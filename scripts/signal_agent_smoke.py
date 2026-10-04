from __future__ import annotations

from sqlalchemy import select

from app.agents.research import ResearchResult
from app.agents.signals import SignalAgent
from app.config import get_settings
from app.database import Base, SessionLocal, engine
from app.models import Account
from app.retrieval.lancedb_store import LanceStore
import app.models  # noqa: F401


RESEARCH_REQUEST = "recent digital transformation and technology developments"


def main() -> None:
    settings = get_settings()
    if not settings.gemini_api_key or not settings.gemini_model:
        raise SystemExit(
            "Gemini configuration missing: set GEMINI_API_KEY and "
            "GEMINI_MODEL in the environment or .env."
        )

    Base.metadata.create_all(engine)

    with SessionLocal() as db:
        account = db.scalar(
            select(Account).where(Account.name == "Schneider Electric")
        )
        if account is None:
            raise SystemExit(
                "Schneider Electric is not present in the configured database."
            )

        result = SignalAgent(
            db=db,
            lance_store=LanceStore(),
            account_name=account.name,
            industry=account.industry,
            market=account.market,
            research_request=RESEARCH_REQUEST,
            top_k=5,
        ).run(
            ResearchResult(
                account_id=str(account.id),
                status="COMPLETED",
            )
        )

    print(f"Status: {result.status}")
    print(f"Signals: {len(result.signals)}")
    for signal in result.signals:
        print(f"\n[{signal.signal_type}] {signal.title}")
        print(f"Claim type: {signal.claim_type}")
        print(f"Confidence: {signal.confidence:.2f}")
        print(f"Description: {signal.description}")
        print("Evidence:")
        for reference in signal.evidence:
            print(
                f"- {reference.document_id} / {reference.chunk_id}"
                f" / {reference.source_url}"
            )

    if result.research_gaps:
        print("\nResearch gaps:")
        for gap in result.research_gaps:
            print(f"- {gap}")


if __name__ == "__main__":
    main()
