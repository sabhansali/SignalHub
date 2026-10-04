from __future__ import annotations

from datetime import datetime
import re
from typing import Protocol
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.ingestion.gdelt import NewsResult, search_news
from app.ingestion.service import IngestResult, ingest_web_document
from app.ingestion.web import _suggest_source_type
from app.models import Source
from app.retrieval.lancedb_store import LanceStore, RetrievedChunk


TOPIC_STOP_WORDS = {
    "and",
    "are",
    "for",
    "from",
    "how",
    "into",
    "its",
    "the",
    "this",
    "what",
    "with",
}


class ResearchInput(BaseModel):
    account_id: str
    account_name: str
    industry: str | None = None
    market: str | None = None
    research_request: str


class SourceFound(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str
    title: str
    source_type: str = "NEWS"
    retrieved_at: datetime
    published_at: datetime | None = None
    source_id: str | None = None
    document_id: str | None = None


class DocumentAdded(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str
    document_id: str
    url: str | None = None
    title: str
    source_type: str = "NEWS"
    retrieved_at: datetime
    chunk_count: int = Field(ge=0)
    changed: bool
    relevant: bool = False


class ResearchResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: str
    sources_found: list[SourceFound] = Field(default_factory=list)
    documents_added: list[DocumentAdded] = Field(default_factory=list)
    research_gaps: list[str] = Field(default_factory=list)
    status: str


class NewsSearcher(Protocol):
    def __call__(
        self,
        query: str,
        days: int = 30,
        max_records: int = 20,
    ) -> list[NewsResult]: ...


class DocumentIngester(Protocol):
    def __call__(
        self,
        db: Session,
        account_id: UUID,
        url: str,
        source_type: str = "OTHER",
        publisher: str | None = None,
        published_at: datetime | None = None,
        lance_store: LanceStore | None = None,
        **kwargs: object,
    ) -> IngestResult: ...


class EvidenceRetriever(Protocol):
    def __call__(
        self,
        query: str,
        account_id: str | None = None,
        top_k: int = 8,
    ) -> list[RetrievedChunk]: ...


class ResearchAgent:
    """Discover and ingest public evidence for one account research request."""

    def __init__(
        self,
        db: Session,
        *,
        lance_store: LanceStore | None = None,
        searcher: NewsSearcher = search_news,
        ingester: DocumentIngester = ingest_web_document,
        retriever: EvidenceRetriever | None = None,
        days: int = 30,
        max_records: int = 20,
    ) -> None:
        self.db = db
        self.lance_store = lance_store
        self.searcher = searcher
        self.ingester = ingester
        self.retriever = retriever or self._retrieve
        self.days = days
        self.max_records = max_records

    def run(self, request: ResearchInput) -> ResearchResult:
        query = self._build_query(request)
        topic_terms = self._topic_terms(request.research_request)
        result = ResearchResult(
            account_id=request.account_id,
            status="COMPLETED",
        )
        search_failed = False

        try:
            discovered = self.searcher(
                query,
                days=self.days,
                max_records=self.max_records,
            )
        except Exception as exc:
            result.research_gaps.append(
                f"Approved-source search failed: {exc}"
            )
            discovered = []
            search_failed = True

        if not discovered and not search_failed:
            result.research_gaps.append(
                "No relevant approved public sources were found."
            )

        seen_urls: set[str] = set()
        ingestion_failed = False
        retrieved_at = datetime.now().astimezone()

        for source in discovered:
            if source.url in seen_urls:
                continue
            seen_urls.add(source.url)

            source_record = SourceFound(
                url=source.url,
                title=source.title,
                source_type=self._source_type(source),
                retrieved_at=retrieved_at,
                published_at=source.published_at,
            )

            try:
                ingested = self.ingester(
                    self.db,
                    UUID(request.account_id),
                    source.url,
                    source_type=source_record.source_type,
                    published_at=source.published_at,
                    lance_store=self.lance_store,
                )
            except Exception as exc:
                ingestion_failed = True
                result.research_gaps.append(
                    f"Could not ingest {source.url}: {exc}"
                )
                result.sources_found.append(source_record)
                continue

            source_record.source_id = str(ingested.source_id)
            source_record.document_id = str(ingested.document_id)
            result.sources_found.append(source_record)
            result.documents_added.append(
                DocumentAdded(
                    source_id=str(ingested.source_id),
                    document_id=str(ingested.document_id),
                    url=source.url,
                    title=source.title,
                    source_type=source_record.source_type,
                    retrieved_at=retrieved_at,
                    chunk_count=ingested.chunk_count,
                    changed=ingested.changed,
                )
            )

        relevant_chunks: list[RetrievedChunk] = []
        try:
            retrieved_chunks = self.retriever(
                query,
                account_id=request.account_id,
                top_k=self.max_records,
            )
            relevant_chunks = self._rank_relevant_chunks(
                retrieved_chunks,
                topic_terms,
            )
            relevant_ids = {
                chunk.document_id
                for chunk in relevant_chunks
            }
        except Exception as exc:
            relevant_ids = set()
            result.research_gaps.append(
                f"Relevant-document retrieval failed: {exc}"
            )

        existing_document_ids = {
            document.document_id
            for document in result.documents_added
        }

        for document in result.documents_added:
            document.relevant = document.document_id in relevant_ids

        seen_fallback_document_ids = set(existing_document_ids)
        for chunk in relevant_chunks:
            if chunk.document_id in seen_fallback_document_ids:
                continue
            seen_fallback_document_ids.add(chunk.document_id)

            result.documents_added.append(
                self._fallback_document(chunk)
            )

        if not relevant_ids:
            result.research_gaps.append(
                "No relevant evidence-bearing documents were identified."
            )

        if search_failed and not relevant_ids:
            result.status = "FAILED"
        elif ingestion_failed or result.research_gaps:
            result.status = "PARTIAL"
        elif relevant_ids:
            result.status = "COMPLETED"
        else:
            result.status = "PARTIAL"

        return result

    def _retrieve(
        self,
        query: str,
        account_id: str | None = None,
        top_k: int = 8,
    ) -> list[RetrievedChunk]:
        if self.lance_store is None:
            return []
        return self.lance_store.search(
            query,
            account_id=account_id,
            top_k=top_k,
        )

    def _fallback_document(self, chunk: RetrievedChunk) -> DocumentAdded:
        return DocumentAdded(
            source_id=str(getattr(chunk, "source_id", "")),
            document_id=str(chunk.document_id),
            url=self._source_url(getattr(chunk, "source_id", None)),
            title=str(getattr(chunk, "title", "Indexed evidence")),
            source_type=str(getattr(chunk, "source_type", "OTHER")),
            retrieved_at=(
                getattr(chunk, "retrieved_at", None)
                or datetime.now().astimezone()
            ),
            chunk_count=0,
            changed=False,
            relevant=True,
        )

    def _source_url(self, source_id: object) -> str | None:
        if not source_id:
            return None

        db_get = getattr(self.db, "get", None)
        if not callable(db_get):
            return None

        try:
            source = db_get(Source, UUID(str(source_id)))
        except (TypeError, ValueError):
            return None

        return source.url if source is not None else None

    @staticmethod
    def _source_type(source: NewsResult) -> str:
        return _suggest_source_type(
            source.url,
            source.title,
            "NEWS",
        )

    @staticmethod
    def _topic_terms(research_request: str) -> set[str]:
        return {
            term
            for term in re.findall(r"[a-z0-9]+", research_request.lower())
            if len(term) > 2 and term not in TOPIC_STOP_WORDS
        }

    @classmethod
    def _rank_relevant_chunks(
        cls,
        chunks: list[RetrievedChunk],
        topic_terms: set[str],
    ) -> list[RetrievedChunk]:
        ranked = sorted(
            (
                chunk
                for chunk in chunks
                if not cls._is_generic_chunk(chunk, topic_terms)
            ),
            key=lambda chunk: cls._evidence_score(chunk, topic_terms),
            reverse=True,
        )
        seen_document_ids: set[str] = set()
        unique: list[RetrievedChunk] = []
        for chunk in ranked:
            if chunk.document_id in seen_document_ids:
                continue
            seen_document_ids.add(chunk.document_id)
            unique.append(chunk)
        return unique

    @classmethod
    def _is_generic_chunk(
        cls,
        chunk: RetrievedChunk,
        topic_terms: set[str],
    ) -> bool:
        title = str(getattr(chunk, "title", "")).lower()
        generic_title_patterns = (
            "about us",
            "company overview",
            "investor relations",
            "careers",
            "careers overview",
            "newsroom",
            "find what you need",
            "search",
            "products",
            "support",
            "contact us",
            "search results",
            "site map",
        )

        if not any(term in title for term in generic_title_patterns):
            return False

        obvious_navigation_title = (
            title.startswith(
                (
                    "find what you need",
                    "careers overview",
                    "search results",
                    "site map",
                )
            )
            or any(
                title.startswith(term)
                and ("|" in title or len(title.split()) <= 5)
                for term in (
                    "search",
                    "products",
                    "support",
                    "contact us",
                )
            )
        )
        if obvious_navigation_title:
            return True

        evidence_source_types = {
            "ANNUAL_REPORT",
            "EVENT",
            "INVESTOR",
            "NEWS",
            "PARTNER",
            "PRESS_RELEASE",
        }
        if getattr(chunk, "source_type", "") in evidence_source_types:
            return False

        if getattr(chunk, "published_at", None):
            return False

        if getattr(chunk, "document_type", "") != "text/html":
            return False

        return True

    @classmethod
    def _supports_topic(
        cls,
        chunk: RetrievedChunk,
        topic_terms: set[str],
    ) -> bool:
        if not hasattr(chunk, "text") and not hasattr(chunk, "title"):
            return True

        if not topic_terms:
            return True

        content = (
            f"{getattr(chunk, 'title', '')} "
            f"{getattr(chunk, 'text', '')}"
        ).lower()
        content_terms = set(re.findall(r"[a-z0-9]+", content))
        return bool(content_terms.intersection(topic_terms))

    @classmethod
    def _evidence_score(
        cls,
        chunk: RetrievedChunk,
        topic_terms: set[str],
    ) -> float:
        content = (
            f"{getattr(chunk, 'title', '')} "
            f"{getattr(chunk, 'text', '')}"
        ).lower()
        content_terms = set(re.findall(r"[a-z0-9]+", content))
        topic_hits = len(content_terms.intersection(topic_terms))
        specific_source_types = {
            "ANNUAL_REPORT",
            "PRESS_RELEASE",
            "INVESTOR",
            "NEWS",
        }
        source_bonus = (
            0.15
            if getattr(chunk, "source_type", "") in specific_source_types
            else 0.0
        )
        publication_bonus = (
            0.10
            if getattr(chunk, "published_at", None)
            else 0.0
        )
        document_bonus = (
            0.05
            if getattr(chunk, "document_type", "") != "text/html"
            else 0.0
        )
        return (
            float(getattr(chunk, "combined_score", 0.0))
            + source_bonus
            + publication_bonus
            + document_bonus
            + (0.05 * topic_hits)
        )

    @staticmethod
    def _build_query(request: ResearchInput) -> str:
        parts = [request.account_name]
        if request.industry:
            parts.append(request.industry)
        if request.market:
            parts.append(request.market)
        if request.research_request.strip():
            parts.append(request.research_request.strip())
        return " ".join(parts)