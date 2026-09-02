"""JSON API collectors used by enterprise recruiting platforms."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any
from urllib.parse import urlparse

from junior.collectors.contracts import CollectedJob, CollectorSource
from junior.collectors.public_api import _get_json


class OracleHCMCollector:
    source_type = "oracle_hcm"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = _required(source, "source_url")
        site = str(source.source_settings.get("site_number") or "CX")
        referer = str(source.source_settings.get("referer_url") or "")
        page_size = int(source.source_settings.get("page_size", 25))
        max_pages = int(source.source_settings.get("max_pages", 40))
        results: list[CollectedJob] = []
        seen: set[str] = set()
        for page in range(max_pages):
            offset = page * page_size
            payload = _get_json(
                source_url,
                {
                    "onlyData": "true",
                    "expand": (
                        "requisitionList.workLocation,"
                        "requisitionList.otherWorkLocations,"
                        "requisitionList.secondaryLocations,"
                        "flexFieldsFacet.values,"
                        "requisitionList.requisitionFlexFields"
                    ),
                    "finder": (
                        f"findReqs;siteNumber={site},limit={page_size},"
                        f"offset={offset}"
                    ),
                },
                {
                    "User-Agent": "Junior/2.0",
                    "Accept": "application/json",
                    **({"Referer": referer} if referer else {}),
                },
            )
            items = payload.get("items")
            search = (
                items[0]
                if isinstance(items, list)
                and items
                and isinstance(items[0], Mapping)
                else {}
            )
            raw_jobs = search.get("requisitionList") or []
            if not isinstance(raw_jobs, list) or not raw_jobs:
                break
            for raw in raw_jobs:
                if not isinstance(raw, Mapping):
                    continue
                job = _oracle_job(source, source_url, site, referer, raw)
                if job and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    results.append(job)
            total = _integer(search.get("TotalJobsCount")) or 0
            if total and offset + page_size >= total:
                break
        return tuple(results)


class JobSynCollector:
    source_type = "jobsyn"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = _required(source, "source_url")
        page_size = int(source.source_settings.get("page_size", 40))
        max_pages = int(source.source_settings.get("max_pages", 5))
        results: list[CollectedJob] = []
        seen: set[str] = set()
        headers = {
            "User-Agent": "Junior/2.0",
            "Accept": "application/json",
            "X-Origin": str(source.source_settings.get("x_origin") or ""),
        }
        for header, setting in (("Referer", "referer_url"), ("Origin", "origin_url")):
            if source.source_settings.get(setting):
                headers[header] = str(source.source_settings[setting])
        for page in range(1, max_pages + 1):
            payload = _get_json(
                source_url, {"page": page, "num_items": page_size}, headers
            )
            raw_jobs = [
                *(payload.get("featured_jobs") or []),
                *(payload.get("jobs") or []),
            ]
            for raw in raw_jobs:
                if not isinstance(raw, Mapping):
                    continue
                job = _jobsyn_job(source, raw)
                if job and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    results.append(job)
            pagination = payload.get("pagination")
            if not isinstance(pagination, Mapping) or not pagination.get(
                "has_more_pages"
            ):
                break
            total_pages = pagination.get("total_pages")
            if isinstance(total_pages, int) and page >= total_pages:
                break
        return tuple(results)


def _oracle_job(
    source: CollectorSource,
    source_url: str,
    site: str,
    referer: str,
    raw: Mapping[str, Any],
) -> CollectedJob | None:
    title = _text(raw.get("Title"))
    job_id = _text(raw.get("Id"))
    if not title or not job_id:
        return None
    if referer and "/sites/" in referer:
        posting_url = f"{referer.rstrip('/')}/job/{job_id}"
    else:
        parsed = urlparse(source_url)
        posting_url = (
            f"{parsed.scheme}://{parsed.netloc}/hcmUI/CandidateExperience/en/"
            f"sites/{site}/job/{job_id}"
        )
    description = "\n\n".join(
        filter(
            None,
            (
                _text(raw.get(key))
                for key in (
                    "ShortDescriptionStr",
                    "ExternalResponsibilitiesStr",
                    "ExternalQualificationsStr",
                )
            ),
        )
    ) or None
    return CollectedJob(
        job_id,
        source.company_id,
        title,
        _text(raw.get("PrimaryLocation")),
        posting_url,
        description,
        _text(raw.get("WorkplaceType")),
    )


def _jobsyn_job(source: CollectorSource, raw: Mapping[str, Any]) -> CollectedJob | None:
    title = _text(raw.get("title_exact")) or _text(raw.get("title"))
    job_id = _text(raw.get("reqid")) or _text(raw.get("guid")) or _text(raw.get("id"))
    if not title or not job_id:
        return None
    location = _text(raw.get("location_exact"))
    if not location:
        city = _text(raw.get("city_exact"))
        state = _text(raw.get("state_short_exact")) or _text(raw.get("state_short"))
        location = ", ".join(filter(None, (city, state))) or None
    posting_url = next(
        filter(None, (_text(raw.get(key)) for key in ("job_url", "url", "apply_url"))),
        None,
    )
    if not posting_url:
        template = _text(source.source_settings.get("job_url_template"))
        if template:
            posting_url = template.format(
                reqid=job_id,
                guid=raw.get("guid") or "",
                title_slug=raw.get("title_slug") or "",
            )
        else:
            posting_url = str(
                source.source_settings.get("referer_url") or "https://sandia.jobs/jobs/"
            )
            posting_url = f"{posting_url}?q={job_id}"
    return CollectedJob(
        job_id,
        source.company_id,
        title,
        location,
        posting_url,
        _text(raw.get("description")),
    )


def _required(source: CollectorSource, key: str) -> str:
    value = _text(source.source_settings.get(key))
    if not value:
        raise ValueError(f"{source.company_name} requires {key}.")
    return value


def _integer(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
