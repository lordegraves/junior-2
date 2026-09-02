"""Native Ashby and Workday collectors migrated from Junior 1.x."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.request import Request, urlopen

from junior.collectors.contracts import CollectedJob, CollectorSource


class AshbyCollector:
    source_type = "ashby"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        slug = _required_setting(source, "source_slug")
        payload = _request_json(
            f"https://api.ashbyhq.com/posting-api/job-board/{slug}"
            "?includeCompensation=true"
        )
        records = payload.get("jobs")
        if not isinstance(records, list):
            raise ValueError("Ashby response does not contain a jobs list.")
        jobs: list[CollectedJob] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            title = _first_text(record, "title")
            posting_url = _first_text(record, "jobUrl", "applyUrl", "url")
            if not title or not posting_url:
                continue
            source_job_id = _first_text(record, "id") or posting_url
            jobs.append(
                CollectedJob(
                    source_job_id,
                    source.company_id,
                    title,
                    _ashby_location(record),
                    posting_url,
                    _first_text(
                        record,
                        "descriptionPlain",
                        "descriptionHtml",
                        "description",
                    ),
                    salary_text=_ashby_salary(record),
                )
            )
        return tuple(jobs)


class WorkdayCollector:
    source_type = "workday"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = _required_setting(source, "source_url")
        source_base_url = _required_setting(source, "source_base_url")
        limit = int(source.source_settings.get("page_size", 20))
        offset = 0
        jobs: list[CollectedJob] = []
        while True:
            payload = _request_json(
                source_url,
                {
                    "appliedFacets": {},
                    "limit": limit,
                    "offset": offset,
                    "searchText": "",
                },
            )
            records = payload.get("jobPostings")
            if not isinstance(records, list):
                raise ValueError("Workday response does not contain jobPostings.")
            jobs.extend(
                job
                for record in records
                if isinstance(record, Mapping)
                and (job := _workday_job(source, source_base_url, record)) is not None
            )
            offset += limit
            total = payload.get("total")
            if not records or len(records) < limit:
                break
            if isinstance(total, int) and offset >= total:
                break
        return tuple(jobs)


def _workday_job(
    source: CollectorSource,
    source_base_url: str,
    record: Mapping[str, Any],
) -> CollectedJob | None:
    title = _first_text(record, "title")
    external_path = _first_text(record, "externalPath")
    posting_url = _first_text(record, "externalUrl", "url")
    if not posting_url and external_path:
        posting_url = f"{source_base_url.rstrip('/')}/{external_path.lstrip('/')}"
    if not title or not posting_url:
        return None
    job_id = _first_text(record, "jobReqId", "id")
    bullets = record.get("bulletFields")
    if not job_id and isinstance(bullets, list) and bullets:
        job_id = str(bullets[0])
    return CollectedJob(
        job_id or posting_url,
        source.company_id,
        title,
        _workday_location(record),
        posting_url,
        _first_text(record, "description", "jobDescription", "summary"),
    )


def _ashby_location(record: Mapping[str, Any]) -> str | None:
    direct = _first_text(record, "locationName")
    if direct:
        return direct
    location = record.get("location")
    if isinstance(location, Mapping):
        return _first_text(location, "name")
    return str(location) if location else None


def _ashby_salary(record: Mapping[str, Any]) -> str | None:
    compensation = record.get("compensation")
    if not isinstance(compensation, Mapping):
        return None
    summary = _first_text(compensation, "compensationTierSummary")
    if summary:
        return summary
    components = compensation.get("summaryComponents")
    if isinstance(components, list):
        values = tuple(str(component) for component in components if component)
        return ", ".join(values) or None
    return None


def _workday_location(record: Mapping[str, Any]) -> str | None:
    direct = _first_text(record, "locationsText")
    if direct:
        return direct
    locations = record.get("locations")
    if not isinstance(locations, list):
        return None
    names = []
    for location in locations:
        if isinstance(location, Mapping):
            names.append(_first_text(location, "name"))
        elif location:
            names.append(str(location))
    return ", ".join(filter(None, names)) or None


def _required_setting(source: CollectorSource, key: str) -> str:
    value = str(source.source_settings.get(key) or "").strip()
    if not value:
        raise ValueError(f"{source.company_name} requires {key}.")
    return value


def _first_text(record: Mapping[str, Any], *keys: str) -> str | None:
    for key in keys:
        value = record.get(key)
        if value:
            return str(value)
    return None


def _request_json(
    url: str, payload: Mapping[str, Any] | None = None
) -> Mapping[str, Any]:
    data = json.dumps(payload).encode() if payload is not None else None
    request = Request(
        url,
        data=data,
        headers={
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Junior/2.0",
        },
        method="POST" if data is not None else "GET",
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310
        decoded = json.loads(response.read().decode("utf-8"))
    if not isinstance(decoded, Mapping):
        raise ValueError("ATS response must be a JSON object.")
    return decoded
