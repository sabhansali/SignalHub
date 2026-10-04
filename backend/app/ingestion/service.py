from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ingestion.chunker import chunk_text
from app.ingestion.web import (
    FetchedPage,
    fetch_page,
)
from app.models import (
    Document,
    Source,
    SourceType,
)
from app.retrieval.lancedb_store import LanceStore


@dataclass(slots=True)
class IngestResult:
    source_id: UUID
    document_id: UUID
    chunk_count: int
    changed: bool


def _source_type(value: str) -> SourceType:
    try:
        return SourceType(value)
    except ValueError:
        return SourceType.OTHER


def _trust_level(
    source_type: str,
) -> int:
    if source_type in {
        "COMPANY",
        "INVESTOR",
        "ANNUAL_REPORT",
        "PRESS_RELEASE",
        "CAREERS",
        "JOBS",
        "PARTNER",
        "EVENT",
    }:
        return 3

    if source_type == "NEWS":
        return 2

    return 1


def _index_document(
    lance_store: LanceStore,
    account_id: UUID,
    source: Source,
    document: Document,
) -> int:
    chunks = chunk_text(
        document.content
    )

    if not chunks:
        return 0

    rows = [
        {
            "chunk_id": (
                f"{document.id}:{index}"
            ),
            "account_id": str(
                account_id
            ),
            "document_id": str(
                document.id
            ),
            "source_id": str(
                source.id
            ),
            "text": chunk,
            "title": document.title,
            "source_type": source.source_type.value,
            "document_type": (
                document.document_type
                or "unknown"
            ),
            "published_at": (
                source.published_at.isoformat()
                if source.published_at
                else ""
            ),
            "retrieved_at": (
                source.retrieved_at.isoformat()
                if source.retrieved_at
                else ""
            ),
        }
        for index, chunk in enumerate(chunks)
    ]

    lance_store.add_chunks(rows)

    return len(chunks)


def _ingest_single_page(
    db: Session,
    account_id: UUID,
    url: str,
    source_type: str,
    publisher: str | None,
    published_at: datetime | None,
    lance_store: LanceStore | None,
    *,
    discover_links: bool,
    max_discovered_links: int,
) -> tuple[IngestResult, FetchedPage]:
    fetched = fetch_page(
        url,
        parent_source_type=source_type,
        discover=discover_links,
        max_discovered_links=max_discovered_links,
    )

    canonical_url = fetched.url

    existing = db.scalar(
        select(Source).where(
            Source.account_id == account_id,
            Source.url == canonical_url,
        )
    )

    source_datetime = (
        published_at
        or fetched.published_at
    )

    # Existing source: refresh metadata even when content is unchanged.
    if (
        existing is not None
        and existing.content_hash
        == fetched.content_hash
    ):
        existing.source_type = _source_type(
            source_type
        )
        existing.title = fetched.title

        if publisher:
            existing.publisher = publisher

        if source_datetime:
            existing.published_at = source_datetime

        existing.retrieved_at = (
            fetched.fetched_at
        )
        existing.trust_level = _trust_level(
            source_type
        )

        document = db.scalar(
            select(Document)
            .where(
                Document.source_id
                == existing.id
            )
            .order_by(
                Document.created_at.desc()
            )
        )

        db.commit()

        # Re-index if the vector DB was rebuilt.
        indexed_chunks = 0

        if (
            lance_store is not None
            and document is not None
            and not lance_store.has_document(
                str(document.id)
            )
        ):
            indexed_chunks = _index_document(
                lance_store,
                account_id,
                existing,
                document,
            )

        return (
            IngestResult(
                source_id=existing.id,
                document_id=(
                    document.id
                    if document
                    else UUID(int=0)
                ),
                chunk_count=indexed_chunks,
                changed=False,
            ),
            fetched,
        )

    # New source.
    if existing is None:
        source = Source(
            account_id=account_id,
            source_type=_source_type(
                source_type
            ),
            title=fetched.title,
            url=canonical_url,
            publisher=publisher,
            published_at=source_datetime,
            retrieved_at=fetched.fetched_at,
            trust_level=_trust_level(
                source_type
            ),
            content_hash=fetched.content_hash,
        )

        db.add(source)
        db.flush()

    # Existing source with changed content.
    else:
        source = existing

        source.source_type = _source_type(
            source_type
        )
        source.title = fetched.title

        if publisher:
            source.publisher = publisher

        if source_datetime:
            source.published_at = source_datetime

        source.retrieved_at = (
            fetched.fetched_at
        )
        source.trust_level = _trust_level(
            source_type
        )
        source.content_hash = (
            fetched.content_hash
        )

    document = Document(
        source_id=source.id,
        account_id=account_id,
        title=fetched.title,
        content=fetched.text,
        document_type=fetched.content_type,
        language="en",
    )

    db.add(document)
    db.flush()

    chunk_count = 0

    if lance_store is not None:
        chunk_count = _index_document(
            lance_store,
            account_id,
            source,
            document,
        )

    db.commit()

    return (
        IngestResult(
            source_id=source.id,
            document_id=document.id,
            chunk_count=chunk_count,
            changed=True,
        ),
        fetched,
    )


def _ingest_recursive(
    db: Session,
    account_id: UUID,
    url: str,
    source_type: str,
    publisher: str | None,
    published_at: datetime | None,
    lance_store: LanceStore | None,
    *,
    depth: int,
    max_depth: int,
    max_discovered_links: int,
    max_pages: int,
    visited: set[str],
) -> IngestResult | None:
    canonical_input = url.rstrip("/")

    if canonical_input in visited:
        return None

    if len(visited) >= max_pages:
        print(
            "MAX PAGES reached; stopping traversal."
        )
        return None

    visited.add(
        canonical_input
    )

    is_root = depth == 0

    try:
        result, fetched = _ingest_single_page(
            db=db,
            account_id=account_id,
            url=url,
            source_type=source_type,
            publisher=publisher,
            published_at=published_at,
            lance_store=lance_store,
            discover_links=(
                depth < max_depth
            ),
            max_discovered_links=(
                max_discovered_links
            ),
        )

        print(
            f"{source_type}: "
            f"{result.chunk_count} chunks | "
            f"changed={result.changed} | "
            f"{fetched.url}"
        )

        if fetched.published_at:
            print(
                f"  published="
                f"{fetched.published_at.date()}"
            )

    except Exception as exc:
        if is_root:
            raise

        print(
            f"DISCOVERED LINK FAILED: "
            f"{url} | {exc}"
        )

        return None

    if depth >= max_depth:
        return result

    for link in fetched.links:
        if len(visited) >= max_pages:
            print(
                "MAX PAGES reached; "
                "skipping remaining links."
            )
            break

        print(
            f"  -> [{link.score}] "
            f"{link.suggested_source_type}: "
            f"{link.anchor_text[:100]}"
        )

        _ingest_recursive(
            db=db,
            account_id=account_id,
            url=link.url,
            source_type=(
                link.suggested_source_type
            ),
            publisher=publisher,
            published_at=None,
            lance_store=lance_store,
            depth=depth + 1,
            max_depth=max_depth,
            max_discovered_links=(
                max_discovered_links
            ),
            max_pages=max_pages,
            visited=visited,
        )

    return result


def ingest_web_document(
    db: Session,
    account_id: UUID,
    url: str,
    source_type: str = "OTHER",
    publisher: str | None = None,
    published_at: datetime | None = None,
    lance_store: LanceStore | None = None,
    *,
    max_depth: int = 1,
    max_discovered_links: int = 8,
    max_pages: int = 25,
) -> IngestResult:
    visited: set[str] = set()

    result = _ingest_recursive(
        db=db,
        account_id=account_id,
        url=url,
        source_type=source_type,
        publisher=publisher,
        published_at=published_at,
        lance_store=lance_store,
        depth=0,
        max_depth=max_depth,
        max_discovered_links=(
            max_discovered_links
        ),
        max_pages=max_pages,
        visited=visited,
    )

    if result is None:
        raise RuntimeError(
            f"Failed to ingest root URL: {url}"
        )

    return result