from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timezone

from app.config import get_settings


@dataclass(slots=True)
class RetrievedChunk:
    chunk_id: str
    account_id: str
    document_id: str
    text: str
    source_id: str
    title: str
    source_type: str
    document_type: str
    published_at: datetime | None
    retrieved_at: datetime | None
    distance: float | None
    semantic_score: float
    recency_score: float
    source_score: float
    combined_score: float


class LanceStore:
    TABLE_NAME = "document_chunks"

    SOURCE_QUALITY = {
        "ANNUAL_REPORT": 1.00,
        "PRESS_RELEASE": 0.95,
        "INVESTOR": 0.90,
        "COMPANY": 0.88,
        "PARTNER": 0.88,
        "EVENT": 0.82,
        "JOBS": 0.78,
        "NEWS": 0.72,
        "OTHER": 0.55,
    }

    def __init__(
        self,
        path: str | None = None,
        embedding_model_name: str = "BAAI/bge-small-en-v1.5",
    ):
        self.path = (
            path
            or get_settings().lancedb_path
        )
        self.embedding_model_name = (
            embedding_model_name
        )

        self._db = None
        self._model = None
        self._table = None

    def _ensure(self) -> None:
        if self._db is not None:
            return

        try:
            import lancedb
            from sentence_transformers import (
                SentenceTransformer,
            )
        except ImportError as exc:
            raise RuntimeError(
                "LanceDB retrieval dependencies are not installed. "
                "Run `pip install -e .`."
            ) from exc

        self._db = lancedb.connect(
            self.path
        )

        self._model = SentenceTransformer(
            self.embedding_model_name
        )

        try:
            self._table = self._db.open_table(
                self.TABLE_NAME
            )
        except Exception:
            self._table = None

    @staticmethod
    def _parse_datetime(
        value: object,
    ) -> datetime | None:
        if value is None:
            return None

        if isinstance(value, datetime):
            parsed = value
        else:
            text = str(value).strip()

            if not text:
                return None

            try:
                parsed = datetime.fromisoformat(
                    text.replace(
                        "Z",
                        "+00:00",
                    )
                )
            except ValueError:
                return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        )

    @staticmethod
    def _semantic_score(
        distance: float | None,
    ) -> float:
        if distance is None:
            return 0.0

        return 1.0 / (
            1.0 + max(distance, 0.0)
        )

    @staticmethod
    def _recency_score(
        published_at: datetime | None,
        *,
        half_life_days: float = 90.0,
    ) -> float:
        """
        Publication date only.

        We intentionally do NOT use retrieval time because
        fetching an old page today must not make it look new.
        """

        if published_at is None:
            return 0.0

        now = datetime.now(
            timezone.utc
        )

        age_days = max(
            0.0,
            (
                now - published_at
            ).total_seconds()
            / 86400.0,
        )

        return math.exp(
            -math.log(2)
            * age_days
            / half_life_days
        )

    @staticmethod
    def _escape_sql(
        value: str,
    ) -> str:
        return value.replace(
            "'",
            "''",
        )

    def add_chunks(
        self,
        rows: list[dict],
    ) -> int:
        if not rows:
            return 0

        self._ensure()

        texts = [
            row["text"]
            for row in rows
        ]

        vectors = self._model.encode(
            texts,
            normalize_embeddings=True,
        ).tolist()

        records = []

        for row, vector in zip(
            rows,
            vectors,
            strict=True,
        ):
            records.append(
                {
                    **row,
                    "vector": vector,
                }
            )

        if self._table is None:
            self._table = (
                self._db.create_table(
                    self.TABLE_NAME,
                    data=records,
                )
            )
        else:
            self._table.add(
                records
            )

        return len(records)

    def has_document(
    self,
    document_id: str,
) -> bool:
        """
        Check whether a document already exists in LanceDB.

        A simple Arrow-column membership check is sufficient here.
        This is intentionally optimized for correctness and
        portability; our corpus is small during development.
        """
        self._ensure()

        if self._table is None:
            return False

        arrow_table = self._table.to_arrow()

        if "document_id" not in arrow_table.column_names:
            return False

        document_ids = (
            arrow_table["document_id"]
            .to_pylist()
        )

        return str(document_id) in {
            str(value)
            for value in document_ids
        }

    def search(
        self,
        query: str,
        account_id: str | None = None,
        top_k: int = 8,
        *,
        source_types: list[str] | None = None,
        document_type: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        recency_weight: float = 0.10,
        source_weight: float = 0.05,
        candidate_multiplier: int = 8,
    ) -> list[RetrievedChunk]:

        if top_k <= 0:
            raise ValueError(
                "top_k must be positive"
            )

        self._ensure()

        if self._table is None:
            return []

        # IMPORTANT:
        # Explicitly tell LanceDB which column contains
        # the vector and explicitly use cosine distance.
        query_vector = self._model.encode(
            query,
            normalize_embeddings=True,
        ).tolist()

        candidate_k = max(
            top_k * candidate_multiplier,
            40,
        )

        search = (
            self._table.search(
                query_vector,
                vector_column_name="vector",
            )
            .distance_type("cosine")
        )

        # SQL prefilters.
        filters: list[str] = []

        if account_id:
            escaped = self._escape_sql(
                account_id
            )

            filters.append(
                f"account_id = '{escaped}'"
            )

        if source_types:
            values = [
                self._escape_sql(
                    value
                )
                for value in source_types
            ]

            filters.append(
                "("
                + " OR ".join(
                    f"source_type = '{value}'"
                    for value in values
                )
                + ")"
            )

        if document_type:
            escaped = self._escape_sql(
                document_type
            )

            filters.append(
                f"document_type = '{escaped}'"
            )

        if filters:
            search = search.where(
                " AND ".join(filters),
                prefilter=True,
            )

        raw_results = (
            search
            .limit(candidate_k)
            .to_list()
        )

        ranked: list[
            RetrievedChunk
        ] = []

        for row in raw_results:

            distance_raw = row.get(
                "_distance"
            )

            distance = (
                float(distance_raw)
                if distance_raw is not None
                else None
            )

            published_at = (
                self._parse_datetime(
                    row.get(
                        "published_at"
                    )
                )
            )

            retrieved_at = (
                self._parse_datetime(
                    row.get(
                        "retrieved_at"
                    )
                )
            )

            reference_date = (
                published_at
            )

            if (
                date_from is not None
                and (
                    reference_date is None
                    or reference_date
                    < date_from
                )
            ):
                continue

            if (
                date_to is not None
                and (
                    reference_date is None
                    or reference_date
                    > date_to
                )
            ):
                continue

            semantic_score = (
                self._semantic_score(
                    distance
                )
            )

            recency_score = (
                self._recency_score(
                    published_at
                )
            )

            source_type = str(
                row.get(
                    "source_type",
                    "OTHER",
                )
            )

            source_score = (
                self.SOURCE_QUALITY.get(
                    source_type,
                    0.50,
                )
            )

            combined_score = (
                semantic_score
                + (
                    recency_weight
                    * recency_score
                )
                + (
                    source_weight
                    * source_score
                )
            )

            ranked.append(
                RetrievedChunk(
                    chunk_id=str(
                        row["chunk_id"]
                    ),
                    account_id=str(
                        row["account_id"]
                    ),
                    document_id=str(
                        row["document_id"]
                    ),
                    text=str(
                        row["text"]
                    ),
                    source_id=str(
                        row["source_id"]
                    ),
                    title=str(
                        row.get(
                            "title",
                            "",
                        )
                    ),
                    source_type=source_type,
                    document_type=str(
                        row.get(
                            "document_type",
                            "unknown",
                        )
                    ),
                    published_at=published_at,
                    retrieved_at=retrieved_at,
                    distance=distance,
                    semantic_score=semantic_score,
                    recency_score=recency_score,
                    source_score=source_score,
                    combined_score=combined_score,
                )
            )

        ranked.sort(
            key=lambda item: item.combined_score,
            reverse=True,
        )

        # One result per source.
        # This prevents five chunks from the same article
        # from crowding out other evidence.
        selected: list[
            RetrievedChunk
        ] = []

        seen_sources: set[str] = set()

        for item in ranked:

            if item.source_id in seen_sources:
                continue

            selected.append(item)

            seen_sources.add(
                item.source_id
            )

            if len(selected) >= top_k:
                break

        return selected