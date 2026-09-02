"""Collectors for ATS products that embed job data in rendered HTML pages."""

from __future__ import annotations

import json
import re
from collections.abc import Mapping, Sequence
from html import unescape
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from junior.collectors.contracts import CollectedJob, CollectorSource


class RipplingCollector:
    source_type = "rippling"
    _BASE_URL = "https://ats.rippling.com"
    _NEXT_DATA = re.compile(
        r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>',
        re.DOTALL,
    )

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        slug = _required_setting(source, "source_slug")
        first = self._payload(slug, 0)
        pages = _rippling_job_data(first).get("totalPages")
        total_pages = pages if isinstance(pages, int) and pages > 0 else 1
        merged: dict[str, CollectedJob] = {}
        for page in range(total_pages):
            payload = first if page == 0 else self._payload(slug, page)
            for job in _parse_rippling_jobs(source, payload):
                existing = merged.get(job.source_job_id)
                merged[job.source_job_id] = (
                    _merge_rippling_job(existing, job) if existing else job
                )
        return tuple(merged.values())

    def _payload(self, slug: str, page: int) -> Mapping[str, Any]:
        html = _get_html(f"{self._BASE_URL}/{slug}/jobs?page={page}")
        match = self._NEXT_DATA.search(html)
        if not match:
            raise ValueError("Rippling page does not contain __NEXT_DATA__ JSON.")
        try:
            payload = json.loads(unescape(match.group(1)))
        except json.JSONDecodeError as error:
            raise ValueError("Rippling __NEXT_DATA__ JSON is invalid.") from error
        if not isinstance(payload, Mapping):
            raise ValueError("Rippling __NEXT_DATA__ JSON must be an object.")
        return payload


class PhenomCollector:
    source_type = "phenom"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = _required_setting(source, "source_url")
        base_url = str(source.source_settings.get("job_base_url") or source_url)
        page_size = int(source.source_settings.get("page_size", 10))
        max_pages = int(source.source_settings.get("max_pages", 25))
        results: list[CollectedJob] = []
        seen: set[str] = set()
        total_hits: int | None = None
        for page in range(max_pages):
            separator = "&" if "?" in source_url else "?"
            parameters = urlencode({"from": page * page_size, "s": 1})
            html = _get_html(f"{source_url}{separator}{parameters}")
            search = _phenom_search_data(html)
            if search is None:
                break
            if total_hits is None:
                total_hits = _safe_int(search.get("totalHits"))
            data = search.get("data")
            raw_jobs = data.get("jobs") if isinstance(data, Mapping) else None
            if not isinstance(raw_jobs, list) or not raw_jobs:
                break
            for raw_job in raw_jobs:
                if not isinstance(raw_job, Mapping):
                    continue
                job = _parse_phenom_job(source, base_url, raw_job)
                if job is None or job.source_job_id in seen:
                    continue
                seen.add(job.source_job_id)
                results.append(job)
            if total_hits is not None and len(results) >= total_hits:
                break
        return tuple(results)


def _rippling_job_data(payload: Mapping[str, Any]) -> Mapping[str, Any]:
    props = payload.get("props")
    page_props = props.get("pageProps") if isinstance(props, Mapping) else None
    state = (
        page_props.get("dehydratedState")
        if isinstance(page_props, Mapping)
        else None
    )
    queries = state.get("queries") if isinstance(state, Mapping) else None
    if not isinstance(queries, list):
        raise ValueError("Rippling payload does not contain dehydrated queries.")
    for query in queries:
        if not isinstance(query, Mapping):
            continue
        key = query.get("queryKey")
        state = query.get("state")
        data = state.get("data") if isinstance(state, Mapping) else None
        if (
            isinstance(key, list)
            and len(key) >= 3
            and key[2] == "job-posts"
            and isinstance(data, Mapping)
            and isinstance(data.get("items"), list)
        ):
            return data
    raise ValueError("Rippling payload does not contain job-posts items.")


def _parse_rippling_jobs(
    source: CollectorSource, payload: Mapping[str, Any]
) -> list[CollectedJob]:
    results: list[CollectedJob] = []
    for raw in _rippling_job_data(payload)["items"]:
        if not isinstance(raw, Mapping):
            continue
        title = _text(raw.get("name"))
        url = _text(raw.get("url"))
        job_id = _text(raw.get("id")) or url
        if not title or not url or not job_id:
            continue
        locations = raw.get("locations")
        names = _unique_text(
            item.get("name")
            for item in locations or []
            if isinstance(item, Mapping)
        )
        department = raw.get("department")
        department_name = (
            _text(department.get("name")) if isinstance(department, Mapping) else None
        )
        results.append(
            CollectedJob(
                job_id,
                source.company_id,
                title,
                "; ".join(names) or None,
                url,
                f"Department: {department_name}" if department_name else None,
            )
        )
    return results


def _merge_rippling_job(existing: CollectedJob, new: CollectedJob) -> CollectedJob:
    locations = _unique_text(
        part.strip()
        for value in (existing.location, new.location)
        if value
        for part in value.split(";")
    )
    return CollectedJob(
        existing.source_job_id,
        existing.company_id,
        existing.title,
        "; ".join(locations) or None,
        existing.posting_url,
        existing.description or new.description,
    )


def _phenom_search_data(html: str) -> Mapping[str, Any] | None:
    marker = "phApp.ddo = "
    start = html.find(marker)
    if start < 0:
        return None
    raw = _balanced_json_object(html, start + len(marker))
    if raw is None:
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    search = (
        payload.get("eagerLoadRefineSearch")
        if isinstance(payload, Mapping)
        else None
    )
    return search if isinstance(search, Mapping) else None


def _balanced_json_object(text: str, start: int) -> str | None:
    object_start = None
    depth = 0
    in_string = False
    escaped = False
    for index in range(start, len(text)):
        char = text[index]
        if object_start is None:
            if char.isspace():
                continue
            if char != "{":
                return None
            object_start, depth = index, 1
            continue
        if escaped:
            escaped = False
        elif char == "\\":
            escaped = True
        elif char == '"':
            in_string = not in_string
        elif not in_string and char == "{":
            depth += 1
        elif not in_string and char == "}":
            depth -= 1
            if depth == 0:
                return text[object_start : index + 1]
    return None


def _parse_phenom_job(
    source: CollectorSource, base_url: str, raw: Mapping[str, Any]
) -> CollectedJob | None:
    title = _text(raw.get("title"))
    sequence = _text(raw.get("jobSeqNo"))
    if not title or not sequence:
        return None
    job_id = _text(raw.get("reqId")) or _text(raw.get("jobId")) or sequence
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    description_parts = [_text(raw.get("descriptionTeaser"))]
    for label, key in (
        ("Category", "category"),
        ("Subcategory", "subCategory"),
        ("Type", "type"),
        ("Posted Date", "postedDate"),
        ("Job Seq No", "jobSeqNo"),
    ):
        value = _text(raw.get(key))
        if value:
            description_parts.append(f"{label}: {value}")
    return CollectedJob(
        job_id,
        source.company_id,
        title,
        _text(raw.get("location")) or _text(raw.get("cityStateCountry")),
        f"{base_url.rstrip('/')}/job/{sequence}/{slug}",
        "\n\n".join(filter(None, description_parts)) or None,
        _text(raw.get("isremote")),
    )


def _get_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 Junior/2.0",
            "Accept": (
                "text/html,application/xhtml+xml,application/json;q=0.8,"
                "*/*;q=0.7"
            ),
        },
    )
    with urlopen(request, timeout=30) as response:  # noqa: S310
        return response.read().decode("utf-8")


def _required_setting(source: CollectorSource, key: str) -> str:
    value = _text(source.source_settings.get(key))
    if not value:
        raise ValueError(f"{source.company_name} requires {key}.")
    return value


def _unique_text(values: Any) -> list[str]:
    result: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in result:
            result.append(text)
    return result


def _safe_int(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _text(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None
