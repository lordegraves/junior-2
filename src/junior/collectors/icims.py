"""iCIMS paginated HTML collector."""

from __future__ import annotations

from collections.abc import Sequence
from html.parser import HTMLParser
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from junior.collectors.contracts import CollectedJob, CollectorSource
from junior.collectors.embedded_page import _get_html


class ICIMSCollector:
    source_type = "icims"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = str(source.source_settings.get("source_url") or "").strip()
        if not source_url:
            raise ValueError(f"{source.company_name} requires source_url.")
        next_url = _search_url(source_url)
        max_pages = _positive(source.source_settings.get("max_pages"), 5)
        results: list[CollectedJob] = []
        seen: set[str] = set()
        for _page in range(max_pages):
            if not next_url:
                break
            current_url = next_url
            page = _get_html(current_url)
            parser = _JobParser(current_url)
            parser.feed(page)
            for title, url in parser.links:
                if url in seen:
                    continue
                seen.add(url)
                results.append(
                    CollectedJob(
                        _job_id(url) or url,
                        source.company_id,
                        title,
                        None,
                        url,
                        None,
                    )
                )
            pager = _NextParser(current_url)
            pager.feed(page)
            next_url = _iframe_url(pager.next_url) if pager.next_url else None
        return tuple(results)


class _JobParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.href: str | None = None
        self.title_attr: str | None = None
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        href = values.get("href")
        if (
            tag.lower() == "a"
            and href
            and "/jobs/" in href
            and not any(
                value in href
                for value in ("/jobs/intro", "/jobs/search", "/jobs/login")
            )
        ):
            self.href = href
            self.title_attr = values.get("title")
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.href and data.strip():
            self.parts.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or not self.href:
            return
        title = _clean_title(self.title_attr or " ".join(self.parts))
        if title:
            self.links.append((title, urljoin(self.base_url, self.href)))
        self.href = self.title_attr = None
        self.parts = []


class _NextParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.next_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        if tag.lower() == "link" and (values.get("rel") or "").lower() == "next":
            self.next_url = urljoin(self.base_url, values.get("href") or "")


def _search_url(source_url: str) -> str:
    parsed = urlparse(source_url)
    if "/jobs/search" in parsed.path:
        result = source_url
    elif source_url.rstrip("/").endswith("/jobs"):
        result = f"{source_url.rstrip('/')}/search?ss=1&searchRelation=keyword_all"
    else:
        result = f"{source_url.rstrip('/')}/jobs/search?ss=1&searchRelation=keyword_all"
    return _iframe_url(result)


def _iframe_url(url: str) -> str:
    parsed = urlparse(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query["in_iframe"] = "1"
    return urlunparse(parsed._replace(query=urlencode(query)))


def _job_id(url: str) -> str | None:
    parts = [part for part in urlparse(url).path.split("/") if part]
    try:
        index = parts.index("jobs")
    except ValueError:
        return None
    return parts[index + 1] if index + 1 < len(parts) else None


def _clean_title(value: str) -> str:
    title = " ".join(value.split())
    if " - " in title:
        prefix, suffix = title.split(" - ", 1)
        if prefix.isdigit() and suffix.strip():
            return suffix.strip()
    return title


def _positive(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default
