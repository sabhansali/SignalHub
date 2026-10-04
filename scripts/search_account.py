from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone

from app.retrieval.lancedb_store import (
    LanceStore,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Search SignalHub account evidence "
            "with semantic, source, and recency ranking."
        )
    )

    parser.add_argument(
        "query",
        help="Research question or search query.",
    )

    parser.add_argument(
        "--account-id",
        help="Restrict retrieval to one account.",
    )

    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Number of final documents to return.",
    )

    parser.add_argument(
        "--source-type",
        action="append",
        dest="source_types",
        help=(
            "Restrict by source type. "
            "Can be supplied multiple times."
        ),
    )

    parser.add_argument(
        "--document-type",
        help=(
            "Exact document MIME type, "
            "e.g. application/pdf or text/html."
        ),
    )

    parser.add_argument(
        "--recent-days",
        type=int,
        help=(
            "Only return evidence from the last N days."
        ),
    )

    parser.add_argument(
        "--no-recency",
        action="store_true",
        help="Disable the recency boost.",
    )

    args = parser.parse_args()

    date_from = None

    if args.recent_days is not None:
        if args.recent_days <= 0:
            raise ValueError(
                "--recent-days must be positive."
            )

        date_from = (
            datetime.now(
                timezone.utc
            )
            - timedelta(
                days=args.recent_days
            )
        )

    store = LanceStore()

    results = store.search(
        args.query,
        account_id=args.account_id,
        top_k=args.top_k,
        source_types=args.source_types,
        document_type=args.document_type,
        date_from=date_from,
        recency_weight=(
            0.0
            if args.no_recency
            else 0.10
        ),
    )

    if not results:
        print(
            "No matching evidence found."
        )
        return

    for index, result in enumerate(
        results,
        start=1,
    ):
        published = (
            result.published_at.isoformat()
            if result.published_at
            else "unknown"
        )

        print(
            f"\n[{index}] {result.title}"
        )

        print(
            "source="
            f"{result.source_type} "
            "document="
            f"{result.document_type}"
        )

        print(
            f"published={published}"
        )

        print(
            f"distance={result.distance} "
            f"semantic={result.semantic_score:.4f} "
            f"recency={result.recency_score:.4f} "
            f"source_quality={result.source_score:.4f} "
            f"combined={result.combined_score:.4f}"
        )

        print(
            f"document_id={result.document_id}"
        )

        print(
            result.text[:1200]
        )


if __name__ == "__main__":
    main()