from __future__ import annotations

import json

import pytest

from junior.collectors.contracts import CollectorSource
from junior.collectors.embedded_page import PhenomCollector, RipplingCollector


def _source(source_type: str, **settings: object) -> CollectorSource:
    return CollectorSource("acme", "Acme", source_type, settings)


def _rippling_payload(items: list[dict[str, object]], pages: int = 1) -> dict:
    return {
        "props": {
            "pageProps": {
                "dehydratedState": {
                    "queries": [
                        {
                            "queryKey": ["board", "acme", "job-posts"],
                            "state": {
                                "data": {"items": items, "totalPages": pages}
                            },
                        }
                    ]
                }
            }
        }
    }


def _next_data(payload: dict) -> str:
    return (
        '<script id="__NEXT_DATA__" type="application/json">'
        f"{json.dumps(payload)}</script>"
    )


def test_rippling_paginates_and_merges_duplicate_locations(monkeypatch) -> None:
    pages = [
        _rippling_payload(
            [
                {
                    "id": "1",
                    "name": "Systems Engineer",
                    "url": "https://ats.rippling.com/acme/jobs/1",
                    "locations": [{"name": "Remote"}],
                    "department": {"name": "Engineering"},
                }
            ],
            2,
        ),
        _rippling_payload(
            [
                {
                    "id": "1",
                    "name": "Systems Engineer",
                    "url": "https://ats.rippling.com/acme/jobs/1",
                    "locations": [{"name": "Boston, MA"}],
                },
                {
                    "id": "2",
                    "name": "Security Engineer",
                    "url": "https://ats.rippling.com/acme/jobs/2",
                    "locations": [],
                },
            ]
        ),
    ]
    calls: list[str] = []

    def fake_get(url: str) -> str:
        calls.append(url)
        return _next_data(pages[len(calls) - 1])

    monkeypatch.setattr("junior.collectors.embedded_page._get_html", fake_get)
    jobs = RipplingCollector().collect(_source("rippling", source_slug="acme"))

    assert calls == [
        "https://ats.rippling.com/acme/jobs?page=0",
        "https://ats.rippling.com/acme/jobs?page=1",
    ]
    assert len(jobs) == 2
    assert jobs[0].location == "Remote; Boston, MA"
    assert jobs[0].description == "Department: Engineering"


def test_rippling_rejects_missing_job_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "junior.collectors.embedded_page._get_html",
        lambda _url: _next_data({"props": {}}),
    )
    with pytest.raises(ValueError, match="dehydrated queries"):
        RipplingCollector().collect(_source("rippling", source_slug="acme"))


def _phenom_html(jobs: list[dict[str, object]], total: int) -> str:
    payload = {"eagerLoadRefineSearch": {"totalHits": total, "data": {"jobs": jobs}}}
    return f'<script>phApp.ddo = {json.dumps(payload)};</script>'


def test_phenom_paginates_builds_descriptions_and_deduplicates(monkeypatch) -> None:
    pages = [
        _phenom_html(
            [
                {
                    "title": "Systems Engineer",
                    "jobSeqNo": "SEQ1",
                    "reqId": "1",
                    "location": "Boston, MA",
                    "descriptionTeaser": "Build systems with {care}.",
                    "category": "Engineering",
                    "isremote": "Hybrid",
                },
                {"title": "Duplicate", "jobSeqNo": "SEQ1", "reqId": "1"},
            ],
            2,
        ),
        _phenom_html(
            [{"title": "Platform Engineer", "jobSeqNo": "SEQ2", "reqId": "2"}],
            2,
        ),
    ]
    calls: list[str] = []

    def fake_get(url: str) -> str:
        calls.append(url)
        return pages[len(calls) - 1]

    monkeypatch.setattr("junior.collectors.embedded_page._get_html", fake_get)
    jobs = PhenomCollector().collect(
        _source(
            "phenom",
            source_url="https://jobs.acme.com/search?lang=en",
            job_base_url="https://jobs.acme.com/us/en",
            page_size=1,
            max_pages=3,
        )
    )

    assert len(jobs) == 2
    assert calls[-1].endswith("&from=1&s=1")
    assert jobs[0].posting_url.endswith("/job/SEQ1/systems-engineer")
    assert "Build systems with {care}." in (jobs[0].description or "")
    assert "Category: Engineering" in (jobs[0].description or "")
    assert jobs[0].remote_status == "Hybrid"


def test_phenom_stops_when_embedded_payload_is_absent(monkeypatch) -> None:
    monkeypatch.setattr(
        "junior.collectors.embedded_page._get_html", lambda _url: "<html></html>"
    )
    assert (
        PhenomCollector().collect(
            _source("phenom", source_url="https://jobs.acme.com/search")
        )
        == ()
    )
