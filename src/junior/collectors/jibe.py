"""Jibe JSON jobs API collector."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from urllib.parse import urljoin

from junior.collectors.contracts import CollectedJob, CollectorSource
from junior.collectors.public_api import _get_json


class JibeCollector:
    source_type = "jibe"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = _required(source, "source_url")
        page_size = _positive(source.source_settings.get("page_size"), 100)
        max_pages = _positive(source.source_settings.get("max_pages"), 5)
        results: list[CollectedJob] = []
        seen: set[str] = set()
        headers = {"User-Agent": "Junior/2.0", "Accept": "application/json"}
        referer = _text(source.source_settings.get("referer_url"))
        if referer:
            headers["Referer"] = referer
        for page in range(1, max_pages + 1):
            payload = _get_json(
                source_url, {"page": page, "limit": page_size}, headers
            )
            items = payload.get("jobs")
            if not isinstance(items, list):
                raise ValueError("Jibe response jobs field is not a list.")
            page_jobs = [
                job
                for item in items
                if (job := _jibe_job(source, source_url, item)) is not None
            ]
            added = 0
            for job in page_jobs:
                if job.posting_url in seen:
                    continue
                seen.add(job.posting_url)
                results.append(job)
                added += 1
            if not page_jobs or not added:
                break
            total = payload.get("totalCount") or payload.get("count")
            if isinstance(total, int) and len(results) >= total:
                break
        return tuple(results)


def _jibe_job(
    source: CollectorSource, source_url: str, item: object
) -> CollectedJob | None:
    if not isinstance(item, Mapping):
        return None
    nested = item.get("data")
    data = nested if isinstance(nested, Mapping) else item
    title = _text(data.get("title"))
    job_id = _text(data.get("req_id")) or _text(data.get("slug"))
    if not title or not job_id:
        return None
    location = next(
        filter(
            None,
            (
                _text(data.get("full_location")),
                _text(data.get("short_location")),
                _text(data.get("location_name")),
            ),
        ),
        None,
    )
    if not location:
        location = ", ".join(
            filter(
                None,
                (
                    _text(data.get("city")),
                    _text(data.get("state")),
                    _text(data.get("country")),
                ),
            )
        ) or None
    description = "\n\n".join(
        filter(
            None,
            (
                _text(data.get("description")),
                _text(data.get("responsibilities")),
                _text(data.get("qualifications")),
            ),
        )
    ) or None
    salaries: list[str] = []
    for key in ("tags2", "tags3", "tags5", "tags6"):
        for value in data.get(key) or []:
            text = _text(value)
            if text and text not in salaries:
                salaries.append(text)
    template = _text(source.source_settings.get("job_url_template"))
    slug = _text(data.get("slug")) or job_id
    posting_url = (
        template.format(slug=slug)
        if template
        else _text(data.get("apply_url"))
        or urljoin(source_url.rstrip("/") + "/", slug)
    )
    return CollectedJob(
        job_id,
        source.company_id,
        title,
        location,
        posting_url,
        description,
        salary_text=" | ".join(salaries) or None,
    )


def _positive(value: object, default: int) -> int:
    try:
        parsed = int(value) if not isinstance(value, bool) else default
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _required(source: CollectorSource, key: str) -> str:
    value = _text(source.source_settings.get(key))
    if not value:
        raise ValueError(f"{source.company_name} requires {key}.")
    return value


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
