"""SelectMinds careers-page collector."""

from __future__ import annotations

from collections.abc import Sequence
from html.parser import HTMLParser
from urllib.parse import urljoin

from junior.collectors.contracts import CollectedJob, CollectorSource
from junior.collectors.embedded_page import _get_html


class SelectMindsCollector:
    source_type = "selectminds"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = str(source.source_settings.get("source_url") or "").strip()
        if not source_url:
            raise ValueError(f"{source.company_name} requires source_url.")
        parser = _Parser(source_url)
        parser.feed(_get_html(source_url))
        results: list[CollectedJob] = []
        seen: set[str] = set()
        for raw in parser.jobs:
            title = _text(raw.get("title"))
            url = _text(raw.get("url"))
            if not title or not url:
                continue
            job_id = _text(raw.get("id")) or _url_id(url) or url
            if job_id in seen:
                continue
            seen.add(job_id)
            description = _text(raw.get("description"))
            post_date = _text(raw.get("post_date"))
            if post_date:
                description = "\n\n".join(
                    filter(None, (description, f"Post Date: {post_date}"))
                )
            results.append(
                CollectedJob(
                    job_id,
                    source.company_id,
                    title,
                    None,
                    url,
                    description,
                )
            )
        return tuple(results)


class _Parser(HTMLParser):
    def __init__(self, base_url: str) -> None:
        super().__init__()
        self.base_url = base_url
        self.jobs: list[dict[str, str | None]] = []
        self.job: dict[str, str | None] | None = None
        self.capture: str | None = None
        self.pending_value: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = dict(attrs)
        classes = set((values.get("class") or "").split())
        if tag == "a" and "job_link" in classes:
            self.job = {
                "title": "",
                "url": urljoin(self.base_url, values.get("href") or ""),
                "description": None,
                "id": None,
                "post_date": None,
            }
            self.jobs.append(self.job)
            self.capture = "title"
        elif tag == "p" and "jlr_description" in classes and self.job:
            self.capture = "description"
        elif tag == "span" and "field_value" in classes and self.job:
            self.capture = "field"
            self.pending_value = ""

    def handle_endtag(self, tag: str) -> None:
        if tag in {"a", "p"} or (tag == "span" and self.capture == "field"):
            self.capture = None

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text or not self.job:
            return
        if self.capture in {"title", "description"}:
            self.job[self.capture] = _append(self.job.get(self.capture), text)
        elif self.capture == "field":
            self.pending_value = _append(self.pending_value, text)
        elif self.pending_value and text in {"Requisition #", "Post Date"}:
            self.job["id" if text == "Requisition #" else "post_date"] = (
                self.pending_value
            )
            self.pending_value = None


def _url_id(url: str) -> str | None:
    candidate = url.rstrip("/").rsplit("-", 1)[-1]
    return candidate if candidate.isdigit() else None


def _append(existing: str | None, value: str) -> str:
    return f"{existing} {value}" if existing else value


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
