from datetime import datetime, timezone
from uuid import UUID, uuid4

import httpx
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.agents.research import ResearchAgent, ResearchInput
from app.database import Base
from app.ingestion.gdelt import NewsResult
from app.ingestion.service import IngestResult
from app.models import Account, Document, Source, SourceType
from app.retrieval.lancedb_store import RetrievedChunk


ACCOUNT_ID = "11111111-1111-1111-1111-111111111111"


def test_research_agent_discovers_ingests_and_identifies_documents() -> None:
    source_id = uuid4()
    document_id = uuid4()
    captured: dict[str, object] = {}

    def searcher(query: str, days: int, max_records: int) -> list[NewsResult]:
        captured["query"] = query
        captured["days"] = days
        captured["max_records"] = max_records
        published_at = datetime(2026, 9, 1, tzinfo=timezone.utc)
        return [
            NewsResult(
                title="Account expands digital operations",
                url="https://example.com/press-releases/digital-operations",
                domain="example.com",
                published_at=published_at,
                language="English",
            ),
            NewsResult(
                title="Duplicate source",
                url="https://example.com/press-releases/digital-operations",
                domain="example.com",
                published_at=published_at,
                language="English",
            ),
        ]

    def ingester(*args: object, **kwargs: object) -> IngestResult:
        assert args[1] == UUID(ACCOUNT_ID)
        assert kwargs["source_type"] == "PRESS_RELEASE"
        return IngestResult(source_id, document_id, 3, True)

    def retriever(query: str, account_id: str, top_k: int) -> list[object]:
        assert query == "Example Manufacturing India digital operations"
        assert account_id == ACCOUNT_ID
        assert top_k == 20
        return [type("Chunk", (), {"document_id": str(document_id)})()]

    result = ResearchAgent(
        db=object(),
        searcher=searcher,
        ingester=ingester,
        retriever=retriever,
        max_records=20,
    ).run(
        ResearchInput(
            account_id=ACCOUNT_ID,
            account_name="Example",
            industry="Manufacturing",
            market="India",
            research_request="digital operations",
        )
    )

    assert captured == {
        "query": "Example Manufacturing India digital operations",
        "days": 30,
        "max_records": 20,
    }
    assert result.status == "COMPLETED"
    assert len(result.sources_found) == 1
    assert result.sources_found[0].source_type == "PRESS_RELEASE"
    assert result.sources_found[0].retrieved_at is not None
    assert result.sources_found[0].document_id == str(document_id)
    assert result.documents_added[0].relevant is True
    assert result.documents_added[0].retrieved_at is not None
    assert result.research_gaps == []


def test_research_agent_reports_partial_results_when_ingestion_fails() -> None:
    def searcher(*args: object, **kwargs: object) -> list[NewsResult]:
        return [
            NewsResult(
                title="Public update",
                url="https://example.com/news/2",
                domain="example.com",
                published_at=None,
                language=None,
            )
        ]

    def ingester(*args: object, **kwargs: object) -> IngestResult:
        raise RuntimeError("network unavailable")

    result = ResearchAgent(
        db=object(),
        searcher=searcher,
        ingester=ingester,
        retriever=lambda *args, **kwargs: [],
    ).run(
        ResearchInput(
            account_id=ACCOUNT_ID,
            account_name="Example",
            research_request="recent developments",
        )
    )

    assert result.status == "PARTIAL"
    assert result.documents_added == []
    assert result.sources_found[0].document_id is None
    assert "network unavailable" in result.research_gaps[0]


def test_research_agent_uses_canonical_source_type_classification() -> None:
    cases = (
        ("https://example.com/about-us/", "About us", "COMPANY"),
        ("https://example.com/press-releases/update", "Update", "PRESS_RELEASE"),
        ("https://example.com/investor-relations/", "Investor relations", "INVESTOR"),
        (
            "https://example.com/download/annual-report-2025.pdf",
            "Annual report 2025",
            "ANNUAL_REPORT",
        ),
        ("https://example.com/careers/india", "Careers", "JOBS"),
    )

    for url, title, expected_type in cases:
        captured: dict[str, str] = {}

        def ingester(*args: object, **kwargs: object) -> IngestResult:
            captured["source_type"] = str(kwargs["source_type"])
            return IngestResult(uuid4(), uuid4(), 1, True)

        result = ResearchAgent(
            db=object(),
            searcher=lambda *args, url=url, title=title, **kwargs: [
                NewsResult(
                    title=title,
                    url=url,
                    domain="example.com",
                    published_at=None,
                    language="English",
                )
            ],
            ingester=ingester,
            retriever=lambda *args, **kwargs: [],
        ).run(
            ResearchInput(
                account_id=ACCOUNT_ID,
                account_name="Example",
                research_request="company information",
            )
        )

        assert captured["source_type"] == expected_type
        assert result.sources_found[0].source_type == expected_type


def test_research_agent_preserves_unchanged_document_accounting() -> None:
    source_id = uuid4()
    document_id = uuid4()

    result = ResearchAgent(
        db=object(),
        searcher=lambda *args, **kwargs: [
            NewsResult(
                title="Investor relations",
                url="https://example.com/investor-relations/",
                domain="example.com",
                published_at=None,
                language="English",
            )
        ],
        ingester=lambda *args, **kwargs: IngestResult(
            source_id,
            document_id,
            4,
            False,
        ),
        retriever=lambda *args, **kwargs: [],
    ).run(
        ResearchInput(
            account_id=ACCOUNT_ID,
            account_name="Example",
            research_request="investor relations",
        )
    )

    assert result.documents_added[0].changed is False
    assert result.documents_added[0].source_type == "INVESTOR"
    assert result.status == "PARTIAL"
    assert "No relevant evidence" in result.research_gaps[0]


def test_research_agent_prefers_specific_evidence_over_generic_pages() -> None:
    source_id = uuid4()
    generic_document_id = uuid4()
    specific_document_id = uuid4()

    def ingester(*args: object, **kwargs: object) -> IngestResult:
        url = str(args[2])
        document_id = (
            generic_document_id
            if "about-us" in url
            else specific_document_id
        )
        return IngestResult(source_id, document_id, 2, True)

    def retriever(*args: object, **kwargs: object) -> list[RetrievedChunk]:
        return [
            RetrievedChunk(
                chunk_id="generic",
                account_id=ACCOUNT_ID,
                document_id=str(generic_document_id),
                text="Company information and general overview.",
                source_id="generic-source",
                title="About us",
                source_type="COMPANY",
                document_type="text/html",
                published_at=None,
                retrieved_at=None,
                distance=0.05,
                semantic_score=0.95,
                recency_score=0.0,
                source_score=0.88,
                combined_score=1.1,
            ),
            RetrievedChunk(
                chunk_id="specific",
                account_id=ACCOUNT_ID,
                document_id=str(specific_document_id),
                text="The company announced a cloud data platform investment.",
                source_id="specific-source",
                title="Cloud platform investment announced",
                source_type="PRESS_RELEASE",
                document_type="text/html",
                published_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
                retrieved_at=None,
                distance=0.2,
                semantic_score=0.8,
                recency_score=0.9,
                source_score=0.95,
                combined_score=0.95,
            ),
        ]

    result = ResearchAgent(
        db=object(),
        searcher=lambda *args, **kwargs: [
            NewsResult(
                title="About us",
                url="https://example.com/about-us/",
                domain="example.com",
                published_at=None,
                language="English",
            ),
            NewsResult(
                title="Cloud platform investment announced",
                url="https://example.com/press-releases/cloud-platform",
                domain="example.com",
                published_at=None,
                language="English",
            ),
        ],
        ingester=ingester,
        retriever=retriever,
    ).run(
        ResearchInput(
            account_id=ACCOUNT_ID,
            account_name="Example",
            research_request="cloud platform investment",
        )
    )

    relevant = {
        document.document_id
        for document in result.documents_added
        if document.relevant
    }
    assert relevant == {str(specific_document_id)}
    assert result.status == "COMPLETED"


def test_research_agent_reports_unsupported_topic_as_partial() -> None:
    source_id = uuid4()
    document_id = uuid4()

    result = ResearchAgent(
        db=object(),
        searcher=lambda *args, **kwargs: [
            NewsResult(
                title="Company overview",
                url="https://example.com/about-us/",
                domain="example.com",
                published_at=None,
                language="English",
            )
        ],
        ingester=lambda *args, **kwargs: IngestResult(
            source_id,
            document_id,
            2,
            True,
        ),
        retriever=lambda *args, **kwargs: [
            RetrievedChunk(
                chunk_id="overview",
                account_id=ACCOUNT_ID,
                document_id=str(document_id),
                text="General company overview.",
                source_id=str(source_id),
                title="Company overview",
                source_type="COMPANY",
                document_type="text/html",
                published_at=None,
                retrieved_at=None,
                distance=0.1,
                semantic_score=0.9,
                recency_score=0.0,
                source_score=0.88,
                combined_score=1.0,
            )
        ],
    ).run(
        ResearchInput(
            account_id=ACCOUNT_ID,
            account_name="Example",
            research_request="quantum computing hiring",
        )
    )

    assert result.status == "PARTIAL"
    assert result.documents_added[0].relevant is False
    assert "No relevant evidence" in result.research_gaps[0]


def test_search_429_attempts_fallback_retrieval_and_returns_partial() -> None:
    source_id = uuid4()
    document_id = uuid4()
    annual_source_id = uuid4()
    annual_document_id = uuid4()
    captured: dict[str, str] = {}

    class SourceLookup:
        def get(self, model: object, identifier: UUID) -> object | None:
            urls = {
                source_id: "https://example.com/press-releases/battery-storage",
                annual_source_id: "https://example.com/reports/annual-report-2025.pdf",
            }
            url = urls.get(identifier)
            return type("SourceRecord", (), {"url": url})() if url else None

    def searcher(*args: object, **kwargs: object) -> list[NewsResult]:
        response = httpx.Response(
            429,
            request=httpx.Request("GET", "https://api.gdeltproject.org"),
        )
        raise httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=response.request,
            response=response,
        )

    def retriever(
        query: str,
        account_id: str,
        top_k: int,
    ) -> list[RetrievedChunk]:
        captured["query"] = query
        captured["account_id"] = account_id
        return [
            RetrievedChunk(
                chunk_id="navigation-1",
                account_id=ACCOUNT_ID,
                document_id="navigation-document",
                text="Find what you need. Search products, services, and support.",
                source_id="navigation-source",
                title="Find what you need",
                source_type="COMPANY",
                document_type="text/html",
                published_at=None,
                retrieved_at=None,
                distance=0.1,
                semantic_score=0.9,
                recency_score=0.0,
                source_score=0.88,
                combined_score=1.1,
            ),
            RetrievedChunk(
                chunk_id="navigation-2",
                account_id=ACCOUNT_ID,
                document_id="navigation-document",
                text="Find what you need. Search products and support.",
                source_id="navigation-source",
                title="Find what you need | Schneider Electric India",
                source_type="COMPANY",
                document_type="text/html",
                published_at=None,
                retrieved_at=None,
                distance=0.11,
                semantic_score=0.89,
                recency_score=0.0,
                source_score=0.88,
                combined_score=1.09,
            ),
            RetrievedChunk(
                chunk_id="indexed-1",
                account_id=ACCOUNT_ID,
                document_id=str(document_id),
                text="Battery energy storage system press release evidence.",
                source_id=str(source_id),
                title="Schneider Electric Unveils Next-Generation Battery Energy Storage System",
                source_type="PRESS_RELEASE",
                document_type="text/html",
                published_at=datetime(2026, 9, 2, tzinfo=timezone.utc),
                retrieved_at=datetime(2026, 9, 3, tzinfo=timezone.utc),
                distance=0.2,
                semantic_score=0.8,
                recency_score=0.9,
                source_score=0.95,
                combined_score=1.0,
            ),
            RetrievedChunk(
                chunk_id="annual-1",
                account_id=ACCOUNT_ID,
                document_id=str(annual_document_id),
                text="2025 full year financial results and annual report evidence.",
                source_id=str(annual_source_id),
                title="2025 Full Year Financial results",
                source_type="ANNUAL_REPORT",
                document_type="application/pdf",
                published_at=datetime(2026, 2, 25, tzinfo=timezone.utc),
                retrieved_at=datetime(2026, 2, 26, tzinfo=timezone.utc),
                distance=0.3,
                semantic_score=0.7,
                recency_score=0.6,
                source_score=1.0,
                combined_score=0.9,
            ),
        ]

    result = ResearchAgent(
        db=SourceLookup(),
        searcher=searcher,
        retriever=retriever,
    ).run(
        ResearchInput(
            account_id=ACCOUNT_ID,
            account_name="Example",
            industry="Manufacturing",
            market="India",
            research_request="digital transformation",
        )
    )

    assert captured == {
        "query": "Example Manufacturing India digital transformation",
        "account_id": ACCOUNT_ID,
    }
    assert result.status == "PARTIAL"
    assert result.sources_found == []
    assert [
        document.document_id
        for document in result.documents_added
    ] == [str(document_id), str(annual_document_id)]
    assert all(document.changed is False for document in result.documents_added)
    assert all(document.relevant is True for document in result.documents_added)
    assert [document.url for document in result.documents_added] == [
        "https://example.com/press-releases/battery-storage",
        "https://example.com/reports/annual-report-2025.pdf",
    ]
    assert "429 Too Many Requests" in result.research_gaps[0]


def test_search_failure_without_fallback_evidence_returns_failed() -> None:
    captured: dict[str, str] = {}

    def searcher(*args: object, **kwargs: object) -> list[NewsResult]:
        raise RuntimeError("GDELT unavailable")

    def retriever(query: str, account_id: str, top_k: int) -> list[RetrievedChunk]:
        captured["query"] = query
        captured["account_id"] = account_id
        return []

    result = ResearchAgent(
        db=object(),
        searcher=searcher,
        retriever=retriever,
    ).run(
        ResearchInput(
            account_id=ACCOUNT_ID,
            account_name="Example",
            research_request="company updates",
        )
    )

    assert result.status == "FAILED"
    assert captured == {
        "query": "Example company updates",
        "account_id": ACCOUNT_ID,
    }
    assert result.sources_found == []
    assert result.documents_added == []
    assert "GDELT unavailable" in result.research_gaps[0]


def test_fallback_with_deterministic_database_and_retriever() -> None:
    def failing_searcher(*args: object, **kwargs: object) -> list[NewsResult]:
        response = httpx.Response(
            429,
            request=httpx.Request("GET", "https://api.gdeltproject.org"),
        )
        raise httpx.HTTPStatusError(
            "429 Too Many Requests",
            request=response.request,
            response=response,
        )

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)

    account_id = UUID(ACCOUNT_ID)
    press_source_id = uuid4()
    annual_source_id = uuid4()
    press_document_id = uuid4()
    annual_document_id = uuid4()

    with Session(engine) as db:
        db.add(
            Account(
                id=account_id,
                name="Schneider Electric",
                industry="Manufacturing",
                market="India",
            )
        )
        db.add_all(
            [
                Source(
                    id=press_source_id,
                    account_id=account_id,
                    source_type=SourceType.PRESS_RELEASE,
                    title="Battery Energy Storage System",
                    url="https://example.com/press-releases/battery-storage",
                ),
                Source(
                    id=annual_source_id,
                    account_id=account_id,
                    source_type=SourceType.ANNUAL_REPORT,
                    title="2025 Full Year Financial results",
                    url="https://example.com/reports/annual-report-2025.pdf",
                ),
                Document(
                    id=press_document_id,
                    source_id=press_source_id,
                    account_id=account_id,
                    title="Battery Energy Storage System",
                    content="Battery energy storage system evidence.",
                    document_type="text/html",
                ),
                Document(
                    id=annual_document_id,
                    source_id=annual_source_id,
                    account_id=account_id,
                    title="2025 Full Year Financial results",
                    content="Annual report evidence.",
                    document_type="application/pdf",
                ),
            ]
        )
        db.commit()

        def retriever(
            query: str,
            account_id: str,
            top_k: int,
        ) -> list[RetrievedChunk]:
            assert query == (
                "Schneider Electric Manufacturing India "
                "recent digital transformation and technology developments"
            )
            assert account_id == ACCOUNT_ID
            assert top_k == 10
            return [
                RetrievedChunk(
                    chunk_id="press-1",
                    account_id=ACCOUNT_ID,
                    document_id=str(press_document_id),
                    text="Battery energy storage system press release evidence.",
                    source_id=str(press_source_id),
                    title="Schneider Electric Unveils Next-Generation Battery Energy Storage System",
                    source_type="PRESS_RELEASE",
                    document_type="text/html",
                    published_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
                    retrieved_at=None,
                    distance=0.1,
                    semantic_score=0.9,
                    recency_score=0.8,
                    source_score=0.95,
                    combined_score=1.1,
                ),
                RetrievedChunk(
                    chunk_id="annual-1",
                    account_id=ACCOUNT_ID,
                    document_id=str(annual_document_id),
                    text="2025 full year financial results and annual report evidence.",
                    source_id=str(annual_source_id),
                    title="2025 Full Year Financial results",
                    source_type="ANNUAL_REPORT",
                    document_type="application/pdf",
                    published_at=datetime(2026, 2, 25, tzinfo=timezone.utc),
                    retrieved_at=None,
                    distance=0.2,
                    semantic_score=0.8,
                    recency_score=0.6,
                    source_score=1.0,
                    combined_score=1.0,
                ),
                RetrievedChunk(
                    chunk_id="generic-1",
                    account_id=ACCOUNT_ID,
                    document_id="generic-document",
                    text="Find what you need. Search products and support.",
                    source_id="generic-source",
                    title="Find what you need | Schneider Electric India",
                    source_type="PRESS_RELEASE",
                    document_type="text/html",
                    published_at=None,
                    retrieved_at=None,
                    distance=0.05,
                    semantic_score=0.95,
                    recency_score=0.0,
                    source_score=0.95,
                    combined_score=1.2,
                ),
                RetrievedChunk(
                    chunk_id="generic-2",
                    account_id=ACCOUNT_ID,
                    document_id="generic-document",
                    text="Find what you need. Search products and support.",
                    source_id="generic-source",
                    title="Find what you need | Schneider Electric India",
                    source_type="PRESS_RELEASE",
                    document_type="text/html",
                    published_at=None,
                    retrieved_at=None,
                    distance=0.06,
                    semantic_score=0.94,
                    recency_score=0.0,
                    source_score=0.95,
                    combined_score=1.19,
                ),
            ]

        result = ResearchAgent(
            db=db,
            searcher=failing_searcher,
            retriever=retriever,
            max_records=10,
        ).run(
            ResearchInput(
                account_id=ACCOUNT_ID,
                account_name="Schneider Electric",
                industry="Manufacturing",
                market="India",
                research_request=(
                    "recent digital transformation and technology developments"
                ),
            )
        )

    assert result.status == "PARTIAL"
    assert any(
        "Approved-source search failed" in gap
        for gap in result.research_gaps
    )
    assert [
        document.document_id
        for document in result.documents_added
    ] == [str(press_document_id), str(annual_document_id)]
    assert all(document.url for document in result.documents_added)
    assert all(document.relevant for document in result.documents_added)
    assert len({document.document_id for document in result.documents_added}) == len(
        result.documents_added
    )
    assert not any(
        "find what you need" in document.title.lower()
        for document in result.documents_added
    )
    assert any(
        document.source_type in {"PRESS_RELEASE", "ANNUAL_REPORT"}
        for document in result.documents_added
    )


def test_research_agent_reports_failed_search_without_fabricating_sources() -> None:
    def searcher(*args: object, **kwargs: object) -> list[NewsResult]:
        raise RuntimeError("GDELT unavailable")

    result = ResearchAgent(
        db=object(),
        searcher=searcher,
        retriever=lambda *args, **kwargs: [],
    ).run(
        ResearchInput(
            account_id=ACCOUNT_ID,
            account_name="Example",
            research_request="company updates",
        )
    )

    assert result.status == "FAILED"
    assert result.sources_found == []
    assert result.documents_added == []
    assert "GDELT unavailable" in result.research_gaps[0]