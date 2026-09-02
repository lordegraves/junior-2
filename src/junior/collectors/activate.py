"""Activate JSON careers API collector."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from html import unescape
from urllib.parse import urljoin

from junior.collectors.contracts import CollectedJob, CollectorSource
from junior.collectors.public_api import _get_json


class ActivateCollector:
    source_type = "activate"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = _required(source, "source_url")
        base_url = _required(source, "source_base_url")
        page_size = _positive(source.source_settings.get("page_size"), 25)
        max_pages = _positive(source.source_settings.get("max_pages"), 25)
        referer = str(source.source_settings.get("referer_url") or source_url)
        results: list[CollectedJob] = []
        seen: set[str] = set()
        for page in range(max_pages):
            payload = _get_json(
                source_url,
                {"jtStartIndex": page * page_size, "jtPageSize": page_size},
                {
                    "Accept": "application/json",
                    "Referer": referer,
                    "User-Agent": "Junior/2.0",
                    "X-Requested-With": "XMLHttpRequest",
                },
            )
            records = payload.get("Records") or []
            if not isinstance(records, list) or not records:
                break
            for record in records:
                if not isinstance(record, Mapping):
                    continue
                job = _job(source, base_url, record)
                if job and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    results.append(job)
            total = payload.get("TotalRecordCount")
            if isinstance(total, int) and len(results) >= total:
                break
            if len(records) < page_size:
                break
        return tuple(results)


def _job(
    source: CollectorSource, base_url: str, record: Mapping
) -> CollectedJob | None:
    tracking = record.get("TrackingObject")
    tracking = tracking if isinstance(tracking, Mapping) else {}
    title = _clean(tracking.get("TitleJson")) or _clean(record.get("Title"))
    job_id = _clean(record.get("ID"))
    if not title or not job_id:
        return None
    locations = tracking.get("LocationNamesJson") or tracking.get(
        "CityStatesDataAbbrevJson"
    )
    location = (
        _clean(locations[0])
        if isinstance(locations, list) and locations
        else _clean(record.get("CityStateDataAbbrev"))
        or _clean(record.get("LocationName"))
    )
    parts = [
        _clean(tracking.get("ReferenceNumberJson"))
        or _clean(record.get("ReferenceNumber")),
        _clean(tracking.get("DepartmentNameJson"))
        or _clean(record.get("DepartmentName")),
        _clean(tracking.get("PostedDateJson")) or _clean(record.get("PostedDate")),
    ]
    categories = tracking.get("AtsCategoryNamesJson") or tracking.get(
        "ActivateCategoryNamesJson"
    )
    if isinstance(categories, list):
        parts.extend(_clean(value) for value in categories)
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-") or "job"
    return CollectedJob(
        job_id,
        source.company_id,
        title,
        location,
        urljoin(base_url, f"/search/jobdetails/{slug}/{job_id}"),
        " | ".join(filter(None, parts)) or None,
    )


def _positive(value: object, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _required(source: CollectorSource, key: str) -> str:
    value = str(source.source_settings.get(key) or "").strip()
    if not value:
        raise ValueError(f"{source.company_name} requires {key}.")
    return value


def _clean(value: object) -> str | None:
    if value is None:
        return None
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", str(value))).split()) or None
