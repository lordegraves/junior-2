"""Collectors for static careers pages."""

from __future__ import annotations

import re
from collections.abc import Sequence
from html import unescape
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

from junior.collectors.contracts import CollectedJob, CollectorSource
from junior.collectors.embedded_page import _get_html


class HTMLCollector:
    source_type = "html"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = _required(source, "source_url")
        parser = _JobLinkParser(source_url)
        parser.feed(_get_html(source_url))
        results: list[CollectedJob] = []
        seen: set[str] = set()
        for title, url in parser.links:
            if url in seen:
                continue
            seen.add(url)
            title = _clean_link_title(title, url)
            results.append(
                CollectedJob(
                    _numeric_path_id(url) or url,
                    source.company_id,
                    title,
                    _location_from_url(url),
                    url,
                    None,
                )
            )
        return tuple(results)


class WekaCollector:
    source_type = "weka"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = _required(source, "source_url")
        page = _get_html(source_url)
        cards = re.compile(
            r"<div\b(?=[^>]*\bclass=[\"'][^\"']*\bmrkto-job\b[^\"']*[\"'])"
            r"(?P<attrs>[^>]*)>(?P<body>.*?)<div class=[\"']cta-box[\"']>",
            re.I | re.S,
        )
        results: list[CollectedJob] = []
        seen: set[str] = set()
        for card in cards.finditer(page):
            body, attrs = card.group("body"), card.group("attrs")
            job_id = _match(r"href=[\"']\?gh_jid=(\d+)[\"']", body)
            title = _clean_markup(_match(r"<h3>(.*?)</h3>", body, re.I | re.S))
            if not job_id or not title or job_id in seen:
                continue
            seen.add(job_id)
            location = _clean_markup(
                _match(r"<div class=[\"']location[\"']>(.*?)</div>", body, re.I | re.S)
            )
            department = _clean_markup(
                _match(r"data-departments=[\"']([^\"']+)[\"']", attrs, re.I)
            )
            results.append(
                CollectedJob(
                    job_id,
                    source.company_id,
                    title,
                    location,
                    urljoin(source_url, f"?gh_jid={job_id}#career-position"),
                    department,
                )
            )
        return tuple(results)


class _JobLinkParser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.current: str | None = None
        self.parts: list[str] = []
        self.links: list[tuple[str, str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        values = dict(attrs)
        href = values.get("href")
        classes = set((values.get("class") or "").split())
        valid_class = bool(
            classes
            & {"jobTitle-link", "results-list__item-title--link", "list-item__link"}
        )
        valid_id = (values.get("id") or "").startswith("link_job_title_")
        if (
            href
            and (valid_class or valid_id)
            and any(part in href for part in ("/job/", "/job-opening/", "/jobs/"))
        ):
            self.current = href
            self.parts = []

    def handle_data(self, data: str) -> None:
        if self.current and data.strip():
            self.parts.append(data.strip())

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "a" and self.current:
            title = " ".join(self.parts).strip()
            if title:
                self.links.append(
                    (unescape(title), urljoin(self.base_url, self.current))
                )
            self.current = None
            self.parts = []


def _numeric_path_id(url: str) -> str | None:
    for part in reversed([part for part in urlparse(url).path.split("/") if part]):
        if part.isdigit():
            return part
    return None


def _location_from_url(url: str) -> str | None:
    parts = [part for part in urlparse(url).path.split("/") if part]
    if len(parts) < 2:
        return None
    slug = parts[-2].split("-")
    if len(slug) >= 4 and slug[-2].isalpha() and slug[-1].isdigit():
        if slug[:2] == ["Oak", "Ridge"]:
            return f"Oak Ridge, {slug[-2]}"
    return None


def _clean_link_title(title: str, url: str) -> str:
    normalized = " ".join(title.split())
    if "/job-opening/" in url:
        return re.split(
            r"\s+(?:MBARI|The|Located|Reporting|This|Applicants)\b",
            normalized,
            maxsplit=1,
        )[0].strip()
    return normalized


def _match(pattern: str, value: str, flags: int = 0) -> str | None:
    match = re.search(pattern, value, flags)
    return match.group(1) if match else None


def _clean_markup(value: str | None) -> str | None:
    if value is None:
        return None
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", value)).split()) or None


def _required(source: CollectorSource, key: str) -> str:
    value = str(source.source_settings.get(key) or "").strip()
    if not value:
        raise ValueError(f"{source.company_name} requires {key}.")
    return value
