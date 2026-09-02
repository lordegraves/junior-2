"""Native collectors for the public Greenhouse and Lever job APIs."""

from __future__ import annotations

import html
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.request import Request, urlopen

from junior.collectors.contracts import CollectedJob, CollectorSource

_TAG = re.compile(r"<[^>]+>")


class PublicJsonCollector:
    def __init__(self, source_type: str, timeout_seconds: float = 30) -> None:
        if source_type not in {"greenhouse", "lever"}:
            raise ValueError(f"Unsupported JSON collector: {source_type}")
        self._source_type = source_type
        self._timeout_seconds = timeout_seconds

    @property
    def source_type(self) -> str:
        return self._source_type

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        slug = str(source.source_settings.get("source_slug") or "").strip()
        if not slug:
            raise ValueError(f"{source.company_name} requires a source slug.")
        url = self._api_url(slug)
        request = Request(url, headers={"User-Agent": "Junior/2.0"})
        with urlopen(request, timeout=self._timeout_seconds) as response:  # noqa: S310
            payload = json.loads(response.read().decode("utf-8"))
        records = payload.get("jobs", ()) if isinstance(payload, Mapping) else payload
        return tuple(self._convert(source, record) for record in records)

    def _api_url(self, slug: str) -> str:
        if self.source_type == "greenhouse":
            return f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        return f"https://api.lever.co/v0/postings/{slug}?mode=json"

    def _convert(
        self, source: CollectorSource, record: Mapping[str, Any]
    ) -> CollectedJob:
        if self.source_type == "greenhouse":
            location = record.get("location") or {}
            return CollectedJob(
                source_job_id=str(record["id"]),
                company_id=source.company_id,
                title=str(record["title"]),
                location=str(location.get("name") or "") or None,
                posting_url=str(record["absolute_url"]),
                description=_plain_text(str(record.get("content") or "")),
            )
        categories = record.get("categories") or {}
        description = "\n".join(
            str(record.get(key) or "")
            for key in ("descriptionPlain", "additionalPlain")
        )
        return CollectedJob(
            source_job_id=str(record["id"]),
            company_id=source.company_id,
            title=str(record["text"]),
            location=str(categories.get("location") or "") or None,
            posting_url=str(record["hostedUrl"]),
            description=_plain_text(description),
        )


def _plain_text(value: str) -> str | None:
    text = html.unescape(_TAG.sub(" ", value))
    clean = " ".join(text.split())
    return clean or None
