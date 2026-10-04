from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx


GDELT_DOC_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


@dataclass(slots=True)
class NewsResult:
    title: str
    url: str
    domain: str | None
    published_at: datetime | None
    language: str | None


def search_news(query: str, days: int = 30, max_records: int = 20) -> list[NewsResult]:
    """Discover recent news through the public GDELT DOC 2.0 API."""
    if not query.strip():
        raise ValueError("query must not be empty")
    if days <= 0 or max_records <= 0:
        raise ValueError("days and max_records must be positive")

    end = datetime.now(timezone.utc)
    start = end - timedelta(days=days)
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": max_records,
        "format": "json",
        "sort": "datedesc",
        "startdatetime": start.strftime("%Y%m%d%H%M%S"),
        "enddatetime": end.strftime("%Y%m%d%H%M%S"),
    }

    with httpx.Client(timeout=20, follow_redirects=True) as client:
        response = client.get(GDELT_DOC_URL, params=params)
        response.raise_for_status()
        payload = response.json()

    articles = payload.get("articles", [])
    results: list[NewsResult] = []
    for article in articles:
        raw_date = article.get("seendate")
        published_at = None
        if raw_date:
            try:
                published_at = datetime.strptime(raw_date[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            except ValueError:
                pass
        results.append(
            NewsResult(
                title=str(article.get("title", "Untitled")),
                url=str(article.get("url", "")),
                domain=article.get("domain"),
                published_at=published_at,
                language=article.get("language"),
            )
        )
    return [r for r in results if r.url]
