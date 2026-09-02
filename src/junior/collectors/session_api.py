"""Collectors for recruiting APIs that require browser-like session setup."""

from __future__ import annotations

import html
import json
import re
import time
from collections.abc import Mapping, Sequence
from http.cookiejar import CookieJar
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse
from urllib.request import HTTPCookieProcessor, Request, build_opener

from junior.collectors.contracts import CollectedJob, CollectorSource


class ADPCollector:
    source_type = "adp"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        source_url = _required(source, "source_url")
        cid = _setting_or_query(source, source_url, "cid")
        cc_id = _setting_or_query(source, source_url, "ccId")
        if not cid or not cc_id:
            missing = "cid" if not cid else "ccId"
            raise ValueError(f"ADP {missing} missing for {source.company_name}.")
        page_size = int(source.source_settings.get("page_size", 20))
        max_pages = int(source.source_settings.get("max_pages", 10))
        results: list[CollectedJob] = []
        seen: set[str] = set()
        for page in range(max_pages):
            payload = _fetch_adp_page(
                source_url,
                cid,
                cc_id,
                str(source.source_settings.get("client") or ""),
                str(source.source_settings.get("locale") or "en_US"),
                page * page_size,
                page_size,
            )
            raw_jobs = payload.get("jobRequisitions") or []
            if not isinstance(raw_jobs, list) or not raw_jobs:
                break
            for raw in raw_jobs:
                if not isinstance(raw, Mapping):
                    continue
                job = _adp_job(source, source_url, raw)
                if job and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    results.append(job)
            if len(raw_jobs) < page_size:
                break
        return tuple(results)


class DayforceCollector:
    source_type = "dayforce"

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]:
        portal_url = _required(source, "source_url")
        namespace, board = _dayforce_portal_parts(source, portal_url)
        culture = str(source.source_settings.get("culture_code") or "en-US")
        page_size = int(source.source_settings.get("page_size", 25))
        max_pages = int(source.source_settings.get("max_pages", 20))
        session, token = _start_dayforce_session(portal_url)
        results: list[CollectedJob] = []
        seen: set[str] = set()
        maximum: int | None = None
        for page in range(max_pages):
            payload = _fetch_dayforce_page(
                session,
                portal_url,
                token,
                namespace,
                board,
                culture,
                page * page_size,
            )
            maximum = maximum or _integer(payload.get("maxCount"))
            raw_jobs = payload.get("jobPostings") or []
            if not isinstance(raw_jobs, list) or not raw_jobs:
                break
            for raw in raw_jobs:
                if not isinstance(raw, Mapping):
                    continue
                job = _dayforce_job(source, portal_url, raw)
                if job and job.source_job_id not in seen:
                    seen.add(job.source_job_id)
                    results.append(job)
            if maximum is not None and len(results) >= maximum:
                break
        return tuple(results)


def _fetch_adp_page(
    source_url: str,
    cid: str,
    cc_id: str,
    client: str,
    locale: str,
    skip: int,
    top: int,
) -> Mapping[str, Any]:
    parsed = urlparse(source_url)
    api_url = (
        f"{parsed.scheme}://{parsed.netloc}/mascsr/default/careercenter/public/"
        "events/staffing/v1/job-requisitions"
    )
    parameters = urlencode(
        {
            "cid": cid,
            "client": client,
            "timeStamp": int(time.time() * 1000),
            "ccId": cc_id,
            "lang": locale,
            "locale": locale,
            "$skip": skip,
            "$top": top,
            "userQuery": "",
        }
    )
    return _request_json(
        Request(
            f"{api_url}?{parameters}",
            headers={
                "User-Agent": "Mozilla/5.0 Junior/2.0",
                "Accept": "application/json",
                "X-Requested-With": "XMLHttpRequest",
                "Referer": source_url,
            },
        )
    )


def _adp_job(
    source: CollectorSource, source_url: str, raw: Mapping[str, Any]
) -> CollectedJob | None:
    title = _clean(raw.get("requisitionTitle"))
    job_id = _clean(raw.get("itemID"))
    if not title or not job_id:
        return None
    locations: list[str] = []
    for location in raw.get("requisitionLocations") or []:
        if not isinstance(location, Mapping):
            continue
        name = location.get("nameCode")
        value = _clean(name.get("shortName")) if isinstance(name, Mapping) else None
        if not value:
            address = location.get("address")
            if isinstance(address, Mapping):
                region = address.get("countrySubdivisionLevel1")
                value = ", ".join(
                    filter(
                        None,
                        (
                            _clean(address.get("cityName")),
                            _clean(region.get("codeValue"))
                            if isinstance(region, Mapping)
                            else None,
                            _clean(address.get("postalCode")),
                        ),
                    )
                ) or None
        if value and value not in locations:
            locations.append(value)
    custom_lines, salary = _adp_custom_fields(raw)
    work_level = raw.get("workLevelCode")
    description = "\n\n".join(
        filter(
            None,
            (
                _clean(raw.get("clientRequisitionID")),
                _clean(raw.get("postDate")),
                _clean(work_level.get("shortName"))
                if isinstance(work_level, Mapping)
                else None,
                "\n".join(custom_lines) or None,
            ),
        )
    ) or None
    if not salary:
        salary = _adp_pay_range(raw)
    location_text = "; ".join(locations) or None
    return CollectedJob(
        job_id,
        source.company_id,
        title,
        location_text,
        _adp_job_url(source_url, job_id),
        description,
        "Remote" if location_text and "remote" in location_text.lower() else None,
        salary,
    )


def _adp_custom_fields(raw: Mapping[str, Any]) -> tuple[list[str], str | None]:
    group = raw.get("customFieldGroup")
    if not isinstance(group, Mapping):
        return [], None
    lines: list[str] = []
    salary = None
    for group_name in ("stringFields", "codeFields"):
        for field in group.get(group_name) or []:
            if not isinstance(field, Mapping):
                continue
            name = field.get("nameCode")
            label = _clean(name.get("codeValue")) if isinstance(name, Mapping) else None
            value = _clean(field.get("stringValue")) or _clean(field.get("shortName"))
            if label and value:
                lines.append(f"{label}: {value}")
                if label == "SalaryRange":
                    salary = value
    return lines, salary


def _adp_pay_range(raw: Mapping[str, Any]) -> str | None:
    pay_range = raw.get("payGradeRange")
    if not isinstance(pay_range, Mapping):
        return None
    minimum = pay_range.get("minimumRate")
    maximum = pay_range.get("maximumRate")
    if not isinstance(minimum, Mapping) or not isinstance(maximum, Mapping):
        return None
    low, high = minimum.get("amountValue"), maximum.get("amountValue")
    if low is None or high is None:
        return None
    currency = _clean(minimum.get("currencyCode")) or _clean(
        maximum.get("currencyCode")
    )
    return f"{low} - {high}{f' {currency}' if currency else ''}"


def _adp_job_url(source_url: str, job_id: str) -> str:
    parsed = urlparse(source_url)
    query = parse_qs(parsed.query, keep_blank_values=True)
    query.update({"jobId": [job_id], "selectedMenuKey": ["CurrentOpenings"]})
    return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))


def _start_dayforce_session(portal_url: str) -> tuple[Any, str]:
    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    opener.open(Request(portal_url, headers={"User-Agent": "Junior/2.0"}), timeout=30)
    parsed = urlparse(portal_url)
    payload = _request_json(
        Request(
            f"{parsed.scheme}://{parsed.netloc}/api/auth/csrf",
            headers={"User-Agent": "Junior/2.0", "Referer": portal_url},
        ),
        opener,
    )
    token = _clean(payload.get("csrfToken"))
    if not token:
        raise ValueError("Dayforce CSRF token was missing.")
    return opener, token


def _fetch_dayforce_page(
    opener: Any,
    portal_url: str,
    token: str,
    namespace: str,
    board: str,
    culture: str,
    offset: int,
) -> Mapping[str, Any]:
    parsed = urlparse(portal_url)
    body = json.dumps(
        {
            "clientNamespace": namespace,
            "jobBoardCode": board,
            "cultureCode": culture,
            "searchText": "",
            "paginationStart": offset,
        }
    ).encode()
    return _request_json(
        Request(
            f"{parsed.scheme}://{parsed.netloc}/api/geo/{namespace}/jobposting/search",
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-CSRF-TOKEN": token,
                "Referer": portal_url,
            },
        ),
        opener,
    )


def _dayforce_job(
    source: CollectorSource, portal_url: str, raw: Mapping[str, Any]
) -> CollectedJob | None:
    title = _clean(raw.get("jobTitle"))
    job_id = _clean(raw.get("jobPostingId"))
    if not title or not job_id:
        return None
    locations: list[str] = []
    for location in raw.get("postingLocations") or []:
        if isinstance(location, Mapping):
            value = next(
                filter(
                    None,
                    (
                        _clean(location.get("formattedAddress")),
                        _clean(location.get("displayName")),
                        _clean(location.get("name")),
                    ),
                ),
                None,
            )
            if value and value not in locations:
                locations.append(value)
    remote = bool(raw.get("hasVirtualLocation"))
    return CollectedJob(
        job_id,
        source.company_id,
        title,
        "; ".join(locations) or ("Remote" if remote else None),
        f"{portal_url.rstrip('/')}/jobs/{job_id}",
        _strip_html(raw.get("jobDescription")),
        "remote" if remote else None,
    )


def _dayforce_portal_parts(
    source: CollectorSource, source_url: str
) -> tuple[str, str]:
    namespace = _clean(source.source_settings.get("client_namespace"))
    board = _clean(source.source_settings.get("job_board_code"))
    if namespace and board:
        return namespace, board
    parts = [part for part in urlparse(source_url).path.split("/") if part]
    if len(parts) < 2:
        raise ValueError("Dayforce URL must include client namespace and board code.")
    return parts[0], parts[1]


def _request_json(request: Request, opener: Any = None) -> Mapping[str, Any]:
    response = (opener or build_opener()).open(request, timeout=30)
    with response:
        payload = json.loads(response.read().decode())
    if not isinstance(payload, Mapping):
        raise ValueError("Recruiting API response must be a JSON object.")
    return payload


def _setting_or_query(
    source: CollectorSource, source_url: str, key: str
) -> str | None:
    return _clean(source.source_settings.get(key)) or next(
        iter(parse_qs(urlparse(source_url).query).get(key, [])), None
    )


def _required(source: CollectorSource, key: str) -> str:
    value = _clean(source.source_settings.get(key))
    if not value:
        raise ValueError(f"{source.company_name} requires {key}.")
    return value


def _strip_html(value: object) -> str | None:
    text = _clean(value)
    if not text:
        return None
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.I)
    text = re.sub(r"</p\s*>", "\n\n", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip() or None


def _integer(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _clean(value: object) -> str | None:
    text = re.sub(r"\s+", " ", str(value).strip()) if value is not None else ""
    return text or None
