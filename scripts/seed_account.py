from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import select

from app.database import Base, SessionLocal, engine
from app.ingestion.service import ingest_web_document
from app.models import Account, Tier
from app.retrieval.lancedb_store import LanceStore


def main() -> None:
    Base.metadata.create_all(bind=engine)
    seed = json.loads(Path("data/seeds/schneider_electric.json").read_text(encoding="utf-8"))

    lance_store = LanceStore()

    with SessionLocal() as db:
        account = db.scalar(select(Account).where(Account.name == seed["name"]))
        if account is None:
            account = Account(
                name=seed["name"],
                industry=seed["industry"],
                market=seed["market"],
                tier=Tier(seed["tier"]),
                description=seed["description"],
            )
            db.add(account)
            db.commit()
            db.refresh(account)

        print(f"Account: {account.name} ({account.id})")
        for source in seed["sources"]:
            try:
                result = ingest_web_document(
                    db,
                    account.id,
                    source["url"],
                    source_type=source["type"],
                    publisher="Schneider Electric",
                    lance_store=lance_store,
                )
                print(f"{source['type']}: {result.chunk_count} chunks | changed={result.changed} | {source['url']}")
            except Exception as exc:
                print(f"FAILED {source['url']}: {exc}")


if __name__ == "__main__":
    main()
