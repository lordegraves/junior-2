"""SchoolSpring list-and-detail API collector."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import unescape

from junior.collectors.contracts import CollectedJob, CollectorSource
from junior.collectors.public_api import _get_json


class SchoolSpringCollector:
    source_type = "schoolspring"
    _BASE = "https://api.schoolspring.com/api/Jobs"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        domain = str(
            source.source_settings.get("domain_name")
            or source.source_settings.get("source_slug")
            or ""
        ).strip()
        if not domain:
            raise ValueError(
                f"SchoolSpring {source.company_name} requires domain_name."
            )
        page_size = int(source.source_settings.get("page_size", 20))
        max_pages = int(source.source_settings.get("max_pages", 25))
        headers = {
            "User-Agent": "Junior/2.0",
            "Accept": "application/json",
            "Origin": f"https://{domain}",
            "Referer": f"https://{domain}/",
        }
        results: list[CollectedJob] = []
        seen: set[str] = set()
        for page in range(1, max_pages + 1):
            payload = _get_json(
                f"{self._BASE}/GetPagedJobsWithSearch",
                {
                    "domainName": domain,
                    "keyword": "",
                    "location": "",
                    "category": "",
                    "gradelevel": "",
                    "jobtype": "",
                    "organization": "",
                    "page": page,
                    "size": page_size,
                    "sortDateAscending": "false",
                },
                headers,
            )
            raw_jobs = _jobs(payload)
            if not raw_jobs:
                break
            for raw in raw_jobs:
                job_id = _text(raw.get("jobId"))
                title = _text(raw.get("title"))
                if not job_id or not title or job_id in seen:
                    continue
                seen.add(job_id)
                try:
                    detail = _get_json(f"{self._BASE}/{job_id}", {}, headers)
                except (OSError, ValueError):
                    detail = {}
                results.append(_build_job(source, domain, job_id, title, raw, detail))
            if len(raw_jobs) < page_size:
                break
        return tuple(results)


def _jobs(payload: Mapping) -> list[Mapping]:
    if payload.get("success") is not True:
        message = payload.get("message") or "unknown"
        raise ValueError(f"SchoolSpring API returned success=false: {message}")
    value = payload.get("value")
    records = value.get("jobsList") if isinstance(value, Mapping) else None
    if not isinstance(records, list):
        raise ValueError("SchoolSpring payload does not contain jobsList.")
    return [record for record in records if isinstance(record, Mapping)]


def _build_job(
    source: CollectorSource,
    domain: str,
    job_id: str,
    title: str,
    raw: Mapping,
    detail: Mapping,
) -> CollectedJob:
    value = detail.get("value") if detail.get("success") is True else {}
    value = value if isinstance(value, Mapping) else {}
    info = value.get("jobInfo")
    info = info if isinstance(info, Mapping) else {}
    locations = [
        text
        for item in value.get("jobLocations") or []
        if isinstance(item, Mapping)
        and (text := _text(item.get("displayLocation"))) is not None
    ]
    categories = []
    for item in value.get("jobCategories") or []:
        if not isinstance(item, Mapping):
            continue
        category = _text(item.get("category"))
        subcategory = _text(item.get("subCategory"))
        label = ": ".join(filter(None, (category, subcategory)))
        if label and label not in categories:
            categories.append(label)
    parts = [_text(info.get("jobDescription"))]
    if employer := _text(raw.get("employer")):
        parts.append(f"Employer: {employer}")
    if deadline := _text(info.get("applicationDeadline")):
        parts.append(f"Application deadline: {deadline}")
    if categories:
        parts.append(f"Categories: {'; '.join(categories)}")
    return CollectedJob(
        job_id,
        source.company_id,
        title,
        "; ".join(dict.fromkeys(locations))
        or _text(raw.get("location")),
        _text(info.get("infoURL")) or f"https://{domain}/?jobId={job_id}",
        "\n\n".join(filter(None, parts)) or None,
    )


def _text(value: object) -> str | None:
    text = " ".join(unescape(str(value)).split()) if value is not None else ""
    return text or None
