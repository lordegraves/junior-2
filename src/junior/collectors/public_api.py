"""SmartRecruiters and USAJobs collectors migrated from Junior 1.x."""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from junior.collectors.contracts import CollectedJob, CollectorSource


class SmartRecruitersCollector:
    source_type = "smartrecruiters"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = _required_setting(source, "source_url")
        identifier = str(
            source.source_settings.get("company_identifier") or source.company_id
        )
        page_size = int(source.source_settings.get("page_size", 100))
        max_pages = int(source.source_settings.get("max_pages", 10))
        jobs: list[CollectedJob] = []
        seen: set[str] = set()
        for page in range(max_pages):
            offset = page * page_size
            payload = _get_json(
                source_url,
                {"limit": page_size, "offset": offset},
            )
            records = payload.get("content") or []
            if not isinstance(records, list) or not records:
                break
            for record in records:
                if not isinstance(record, Mapping):
                    continue
                job = _smartrecruiters_job(source, identifier, record)
                if job is None or job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                jobs.append(job)
            total = int(payload.get("totalFound") or 0)
            if total and offset + page_size >= total:
                break
        return tuple(jobs)


class USAJobsCollector:
    source_type = "usajobs"
    _URL = "https://data.usajobs.gov/api/Search"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        user_agent = os.environ.get("USAJOBS_USER_AGENT")
        authorization_key = os.environ.get("USAJOBS_AUTHORIZATION_KEY")
        if not user_agent or not authorization_key:
            raise ValueError(
                "USAJobs requires USAJOBS_USER_AGENT and "
                "USAJOBS_AUTHORIZATION_KEY."
            )
        query = source.source_settings.get("query_params") or {}
        if not isinstance(query, Mapping):
            raise ValueError("USAJobs query_params must be a mapping.")
        jobs: list[CollectedJob] = []
        for page in range(1, 6):
            params = {
                "Page": page,
                "ResultsPerPage": 100,
                **{str(key): value for key, value in query.items() if value},
            }
            payload = _get_json(
                self._URL,
                params,
                {
                    "Host": "data.usajobs.gov",
                    "User-Agent": user_agent,
                    "Authorization-Key": authorization_key,
                },
            )
            result = payload.get("SearchResult")
            if not isinstance(result, Mapping):
                raise ValueError("USAJobs response is missing SearchResult.")
            records = result.get("SearchResultItems") or []
            if not isinstance(records, list):
                raise ValueError("USAJobs SearchResultItems must be a list.")
            jobs.extend(
                job
                for item in records
                if isinstance(item, Mapping)
                and (job := _usajobs_job(source, item)) is not None
            )
            user_area = result.get("UserArea") or {}
            try:
                total_pages = int(user_area.get("NumberOfPages") or 1)
            except (AttributeError, TypeError, ValueError):
                total_pages = 1
            if page >= total_pages:
                break
        return tuple(jobs)


def _smartrecruiters_job(
    source: CollectorSource,
    identifier: str,
    record: Mapping[str, Any],
) -> CollectedJob | None:
    title = _text(record.get("name"))
    job_id = _text(record.get("id"))
    if not title or not job_id:
        return None
    location_data = record.get("location") or {}
    location = None
    remote_status = None
    if isinstance(location_data, Mapping):
        location = _text(location_data.get("fullLocation"))
        if not location:
            location = ", ".join(
                filter(
                    None,
                    (
                        _text(location_data.get("city")),
                        _text(location_data.get("region")),
                        _text(location_data.get("country")),
                    ),
                )
            ) or None
        if location_data.get("remote") is True:
            remote_status = "Remote"
        elif location_data.get("hybrid") is True:
            remote_status = "Hybrid"
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    url = f"https://jobs.smartrecruiters.com/{identifier}/{job_id}-{slug}"
    description = _smartrecruiters_description(record)
    return CollectedJob(
        job_id,
        source.company_id,
        title,
        location,
        url,
        description,
        remote_status,
    )


def _smartrecruiters_description(record: Mapping[str, Any]) -> str | None:
    parts = [_text(record.get("refNumber"))]
    for key in ("typeOfEmployment", "experienceLevel", "industry", "function"):
        value = record.get(key)
        if isinstance(value, Mapping):
            parts.append(_text(value.get("label")))
    fields = record.get("customField") or []
    if isinstance(fields, list):
        for field in fields:
            if isinstance(field, Mapping):
                label = _text(field.get("fieldLabel"))
                value = _text(field.get("valueLabel"))
                if label and value:
                    parts.append(f"{label}: {value}")
    return "\n\n".join(filter(None, parts)) or None


def _usajobs_job(
    source: CollectorSource, item: Mapping[str, Any]
) -> CollectedJob | None:
    descriptor = item.get("MatchedObjectDescriptor")
    if not isinstance(descriptor, Mapping):
        return None
    job_id = _text(descriptor.get("PositionID"))
    title = _text(descriptor.get("PositionTitle"))
    url = _text(descriptor.get("PositionURI"))
    if not job_id or not title or not url:
        return None
    locations = descriptor.get("PositionLocation") or []
    location = "; ".join(
        filter(
            None,
            (
                _text(entry.get("LocationName"))
                for entry in locations
                if isinstance(entry, Mapping)
            ),
        )
    ) or None
    description = _usajobs_description(descriptor)
    return CollectedJob(job_id, source.company_id, title, location, url, description)


def _usajobs_description(descriptor: Mapping[str, Any]) -> str | None:
    parts = [
        _text(descriptor.get(key))
        for key in (
            "QualificationSummary",
            "MajorDuties",
            "Requirements",
            "Evaluations",
        )
    ]
    user_area = descriptor.get("UserArea")
    details = user_area.get("Details") if isinstance(user_area, Mapping) else None
    if isinstance(details, Mapping):
        for key in (
            "JobSummary",
            "WhoMayApply",
            "TravelCode",
            "SecurityClearance",
            "DrugTestRequired",
        ):
            value = _text(details.get(key))
            if value:
                parts.append(f"{key}: {value}")
    return "\n\n".join(filter(None, parts)) or None


def _get_json(
    url: str,
    parameters: Mapping[str, Any],
    headers: Mapping[str, str] | None = None,
) -> Mapping[str, Any]:
    query = urlencode(parameters)
    request = Request(
        f"{url}{'&' if '?' in url else '?'}{query}",
        headers=dict(headers or {"User-Agent": "Junior/2.0"}),
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310
        payload = json.loads(response.read().decode("utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("ATS response must be a JSON object.")
    return payload


def _required_setting(source: CollectorSource, key: str) -> str:
    value = str(source.source_settings.get(key) or "").strip()
    if not value:
        raise ValueError(f"{source.company_name} requires {key}.")
    return value


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
