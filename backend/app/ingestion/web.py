from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import (
    parse_qsl,
    urlencode,
    urldefrag,
    urljoin,
    urlparse,
    urlunparse,
)

import httpx
from bs4 import BeautifulSoup


TRACKING_PARAMS = {
    "fbclid",
    "gclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
}


@dataclass(slots=True)
class DiscoveredLink:
    url: str
    anchor_text: str
    score: int
    suggested_source_type: str


@dataclass(slots=True)
class FetchedPage:
    url: str
    title: str
    text: str
    content_type: str
    fetched_at: datetime
    published_at: datetime | None
    content_hash: str
    links: list[DiscoveredLink] = field(default_factory=list)


def _hash_text(text: str) -> str:
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def _parse_datetime(
    value: str | None,
) -> datetime | None:
    if not value:
        return None

    value = value.strip()

    # ISO dates / timestamps.
    try:
        parsed = datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        )

    except ValueError:
        pass

    # Common date-only formats.
    formats = (
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%Y-%m-%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
    )

    for fmt in formats:
        try:
            return datetime.strptime(
                value,
                fmt,
            ).replace(
                tzinfo=timezone.utc
            )
        except ValueError:
            continue

    return None


def _looks_like_article_url(
    url: str,
) -> bool:
    path = urlparse(url).path.lower()

    return any(
        marker in path
        for marker in (
            "/press-releases/",
            "/news/",
            "/article/",
            "/articles/",
        )
    )


def _extract_date_from_visible_text(
    text: str,
) -> datetime | None:
    """
    Parse a publication date from visible text.

    This is deliberately used only for article-like URLs;
    generic landing pages can contain dozens of unrelated dates.
    """

    sample = text[:5000]

    patterns = (
        r"\b\d{1,2}/\d{1,2}/\d{4}\b",
        r"\b\d{1,2}-\d{1,2}-\d{4}\b",
        r"\b\d{4}-\d{1,2}-\d{1,2}\b",
        (
            r"\b(?:January|February|March|April|May|June|July|"
            r"August|September|October|November|December) "
            r"\d{1,2}, \d{4}\b"
        ),
        (
            r"\b\d{1,2} "
            r"(?:January|February|March|April|May|June|July|"
            r"August|September|October|November|December) "
            r"\d{4}\b"
        ),
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            sample,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        parsed = _parse_datetime(
            match.group(0)
        )

        if parsed:
            return parsed

    return None


def _extract_published_at(
    soup: BeautifulSoup,
    *,
    page_url: str,
) -> datetime | None:
    """
    Extract publication date conservatively.

    For article/press-release pages:
        Prefer the date visibly associated with the article title.

    For non-article landing pages:
        Return None rather than treating a template/update date
        as the publication date.

    JSON-LD is used only as a fallback because corporate websites
    sometimes expose stale or template-level date metadata.
    """

    path = urlparse(page_url).path.lower()

    article_like = any(
        marker in path
        for marker in (
            "/press-releases/",
            "/news/",
            "/article/",
            "/articles/",
            "/blog/",
        )
    )

    if not article_like:
        return None

    # ---------------------------------------------------------
    # 1. BEST CASE:
    # Find the article title and inspect the nearby visible
    # text for a publication date.
    # ---------------------------------------------------------

    title = ""

    h1 = soup.find("h1")

    if h1:
        title = re.sub(
            r"\s+",
            " ",
            h1.get_text(" ", strip=True),
        ).strip()

    # Prefer <main>, since it normally excludes most
    # global navigation/footer content.
    content_root = (
        soup.find("main")
        or soup.body
        or soup
    )

    visible_text = content_root.get_text(
        "\n",
        strip=True,
    )

    visible_text = re.sub(
        r"\n+",
        "\n",
        visible_text,
    )

    if title:
        title_position = visible_text.lower().find(
            title.lower()
        )

        if title_position >= 0:
            # The article date is normally immediately
            # after the title/breadcrumb/header area.
            nearby_text = visible_text[
                title_position
                + len(title): title_position
                + len(title)
                + 2000
            ]

            parsed = _extract_date_from_visible_text(
                nearby_text
            )

            if parsed:
                return parsed

    # ---------------------------------------------------------
    # 2. Look at explicit <time> elements.
    # ---------------------------------------------------------

    for tag in soup.find_all("time"):
        value = (
            tag.get("datetime")
            or tag.get_text(
                " ",
                strip=True,
            )
        )

        if not value:
            continue

        parsed = _parse_datetime(
            str(value)
        )

        if parsed:
            return parsed

    # ---------------------------------------------------------
    # 3. JSON-LD fallback.
    #
    # We deliberately do this AFTER visible article text.
    # ---------------------------------------------------------

    for script in soup.find_all(
        "script",
        attrs={
            "type": "application/ld+json"
        },
    ):
        raw = (
            script.string
            or script.get_text()
        )

        if not raw.strip():
            continue

        try:
            data = json.loads(raw)
        except (
            json.JSONDecodeError,
            TypeError,
        ):
            continue

        objects: list[dict] = []

        if isinstance(data, dict):
            objects.append(data)

            graph = data.get("@graph")

            if isinstance(graph, list):
                objects.extend(
                    item
                    for item in graph
                    if isinstance(item, dict)
                )

        elif isinstance(data, list):
            objects.extend(
                item
                for item in data
                if isinstance(item, dict)
            )

        for item in objects:
            value = item.get(
                "datePublished"
            )

            if isinstance(value, str):
                parsed = _parse_datetime(
                    value
                )

                if parsed:
                    return parsed

    return None

def _fetch(
    url: str,
    timeout: float,
    max_bytes: int,
) -> tuple[bytes, str, str]:
    parsed = urlparse(url)

    if parsed.scheme not in {
        "http",
        "https",
    } or not parsed.netloc:
        raise ValueError(
            "url must be an absolute HTTP(S) URL"
        )

    headers = {
        "User-Agent": (
            "SignalHub/0.1 "
            "(+portfolio-research; respectful-fetcher)"
        ),
        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/pdf"
        ),
    }

    with httpx.Client(
        timeout=timeout,
        follow_redirects=True,
        headers=headers,
    ) as client:
        response = client.get(url)
        response.raise_for_status()

        body = response.content

        if len(body) > max_bytes:
            raise ValueError(
                f"Response exceeds max_bytes={max_bytes}"
            )

        return (
            body,
            response.headers.get(
                "content-type",
                "",
            ),
            str(response.url),
        )


def _normalise_url(url: str) -> str:
    """
    Canonicalize URLs while preserving meaningful query parameters.

    Removes:
    - fragments
    - common tracking parameters
    """

    clean_url, _fragment = urldefrag(url)

    parsed = urlparse(clean_url)

    query_items = []

    for key, value in parse_qsl(
        parsed.query,
        keep_blank_values=True,
    ):
        lowered = key.lower()

        if lowered.startswith("utm_"):
            continue

        if lowered in TRACKING_PARAMS:
            continue

        query_items.append(
            (key, value)
        )

    normalized_query = urlencode(
        query_items,
        doseq=True,
    )

    normalized = urlunparse(
        (
            parsed.scheme.lower(),
            parsed.netloc.lower(),
            parsed.path or "/",
            parsed.params,
            normalized_query,
            "",
        )
    )

    return normalized.rstrip("/") or normalized


def _same_domain(
    base_url: str,
    candidate_url: str,
) -> bool:
    base_host = (
        urlparse(base_url).hostname
        or ""
    ).lower()

    candidate_host = (
        urlparse(candidate_url).hostname
        or ""
    ).lower()

    return bool(
        base_host
        and candidate_host
        and base_host == candidate_host
    )


def _looks_like_document(
    url: str,
) -> bool:
    path = urlparse(url).path.lower()

    return path.endswith(
        (
            ".pdf",
            ".doc",
            ".docx",
            ".ppt",
            ".pptx",
            ".xls",
            ".xlsx",
        )
    )


def _suggest_source_type(
    url: str,
    anchor_text: str,
    parent_source_type: str,
) -> str:
    combined = (
        f"{url} {anchor_text}"
    ).lower()

    if _looks_like_document(url):
        if any(
            term in combined
            for term in (
                "annual report",
                "universal registration",
                "financial report",
                "integrated report",
                "results",
            )
        ):
            return "ANNUAL_REPORT"

        return "OTHER"

    if any(
        term in combined
        for term in (
            "press release",
            "press-release",
            "newsroom",
            "/news/",
            "/newsroom/",
        )
    ):
        return "PRESS_RELEASE"

    if any(
        term in combined
        for term in (
            "career",
            "careers",
            "job",
            "jobs",
            "vacancy",
            "vacancies",
        )
    ):
        return "JOBS"

    if any(
        term in combined
        for term in (
            "partner",
            "partnership",
        )
    ):
        return "PARTNER"

    if any(
        term in combined
        for term in (
            "investor",
            "financial results",
            "shareholder",
        )
    ):
        return "INVESTOR"

    if any(
        term in combined
        for term in (
            "event",
            "summit",
            "conference",
            "webinar",
        )
    ):
        return "EVENT"

    if any(
        term in combined
        for term in (
            "about us",
            "about-us",
            "company profile",
            "company overview",
            "/company/",
        )
    ):
        return "COMPANY"

    return parent_source_type


def _link_score(
    url: str,
    anchor_text: str,
) -> int:
    path = urlparse(url).path.lower()
    text = anchor_text.lower()

    score = 0

    high_value_terms = {
        "press release": 10,
        "press-release": 10,
        "newsroom": 9,
        "/news/": 9,
        "/newsroom/": 9,
        "annual report": 10,
        "universal registration": 10,
        "financial results": 8,
        "investor": 7,
        "partnership": 8,
        "partner": 6,
        "technology": 6,
        "digital": 5,
        "artificial intelligence": 7,
        "ai": 4,
        "cloud": 6,
        "data": 4,
        "innovation": 5,
        "manufacturing": 5,
        "india": 4,
        "career": 5,
        "careers": 5,
        "job": 5,
        "event": 5,
        "summit": 5,
        "conference": 5,
    }

    for term, weight in high_value_terms.items():
        if term in text:
            score += weight

        if term in path:
            score += weight

    if _looks_like_document(url):
        score += 12

    low_value_terms = {
        "privacy": -10,
        "cookie": -10,
        "legal": -8,
        "accessibility": -8,
        "login": -8,
        "contact": -4,
        "search": -5,
        "sitemap": -8,
    }

    for term, weight in low_value_terms.items():
        if term in text or term in path:
            score += weight

    return score


def discover_links(
    page_url: str,
    html: bytes,
    *,
    parent_source_type: str = "OTHER",
    max_links: int = 10,
    min_score: int = 4,
) -> list[DiscoveredLink]:
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    seen: set[str] = set()
    candidates: list[DiscoveredLink] = []

    for anchor in soup.find_all(
        "a",
        href=True,
    ):
        raw_href = str(
            anchor.get("href", "")
        ).strip()

        if not raw_href:
            continue

        if raw_href.startswith(
            (
                "#",
                "mailto:",
                "tel:",
                "javascript:",
            )
        ):
            continue

        absolute_url = _normalise_url(
            urljoin(
                page_url,
                raw_href,
            )
        )

        parsed = urlparse(
            absolute_url
        )

        if parsed.scheme not in {
            "http",
            "https",
        }:
            continue

        if not _same_domain(
            page_url,
            absolute_url,
        ):
            continue

        if absolute_url == _normalise_url(
            page_url
        ):
            continue

        if absolute_url in seen:
            continue

        anchor_text = re.sub(
            r"\s+",
            " ",
            anchor.get_text(
                " ",
                strip=True,
            ),
        )[:300]

        score = _link_score(
            absolute_url,
            anchor_text,
        )

        if score < min_score:
            continue

        seen.add(
            absolute_url
        )

        candidates.append(
            DiscoveredLink(
                url=absolute_url,
                anchor_text=anchor_text,
                score=score,
                suggested_source_type=(
                    _suggest_source_type(
                        absolute_url,
                        anchor_text,
                        parent_source_type,
                    )
                ),
            )
        )

    candidates.sort(
        key=lambda item: item.score,
        reverse=True,
    )

    return candidates[:max_links]


def fetch_page(
    url: str,
    timeout: float = 20.0,
    max_bytes: int = 5_000_000,
    *,
    parent_source_type: str = "OTHER",
    discover: bool = True,
    max_discovered_links: int = 10,
) -> FetchedPage:
    body, content_type, final_url = _fetch(
        url,
        timeout,
        max_bytes,
    )

    final_url = _normalise_url(
        final_url
    )

    fetched_at = datetime.now(
        timezone.utc
    )

    # PDF
    if (
        "pdf" in content_type.lower()
        or final_url.lower().endswith(".pdf")
        or url.lower().endswith(".pdf")
    ):
        try:
            import pymupdf
        except ImportError as exc:
            raise RuntimeError(
                "PyMuPDF is required for PDF ingestion. "
                "Run `pip install -e .`."
            ) from exc

        document = pymupdf.open(
            stream=body,
            filetype="pdf",
        )

        pages = [
            page.get_text("text")
            for page in document
        ]

        text = "\n\n".join(
            pages
        ).strip()

        title = (
            document.metadata.get("title")
            or final_url.rsplit(
                "/",
                1,
            )[-1]
        )

        published_at = None

        metadata = document.metadata or {}

        for key in (
            "creationDate",
            "modDate",
        ):
            value = metadata.get(key)

            if not value:
                continue

            match = re.search(
                r"D:(\d{4})(\d{2})(\d{2})"
                r"(\d{2})?(\d{2})?(\d{2})?",
                str(value),
            )

            if match:
                published_at = datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                    int(match.group(4) or 0),
                    int(match.group(5) or 0),
                    int(match.group(6) or 0),
                    tzinfo=timezone.utc,
                )
                break

        document.close()

        normalized = "\n".join(
            line.strip()
            for line in text.splitlines()
            if line.strip()
        )

        return FetchedPage(
            url=final_url,
            title=title[:500],
            text=normalized,
            content_type="application/pdf",
            fetched_at=fetched_at,
            published_at=published_at,
            content_hash=_hash_text(
                normalized
            ),
            links=[],
        )

    if "html" not in content_type.lower():
        raise ValueError(
            f"Expected HTML/PDF content, "
            f"got {content_type!r}"
        )

    soup = BeautifulSoup(
        body,
        "html.parser",
    )

    published_at = _extract_published_at(
        soup,
        page_url=final_url,
    )

    links: list[DiscoveredLink] = []

    if discover:
        links = discover_links(
            final_url,
            body,
            parent_source_type=parent_source_type,
            max_links=max_discovered_links,
        )

    for tag in soup(
        [
            "script",
            "style",
            "noscript",
            "svg",
        ]
    ):
        tag.decompose()

    title = (
        soup.title.get_text(
            " ",
            strip=True,
        )
        if soup.title
        else "Untitled page"
    )

    text = soup.get_text(
        "\n",
        strip=True,
    )

    normalized = "\n".join(
        line.strip()
        for line in text.splitlines()
        if line.strip()
    )

    return FetchedPage(
        url=final_url,
        title=title[:500],
        text=normalized,
        content_type="text/html",
        fetched_at=fetched_at,
        published_at=published_at,
        content_hash=_hash_text(
            normalized
        ),
        links=links,
    )