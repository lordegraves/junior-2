import pytest

from junior.collectors.contracts import CollectorSource
from junior.collectors.session_api import ADPCollector, DayforceCollector


def _source(source_type: str, **settings: object) -> CollectorSource:
    return CollectorSource("acme", "Acme", source_type, settings)


def test_adp_paginates_deduplicates_and_preserves_salary(monkeypatch) -> None:
    calls: list[int] = []

    def fake_page(source_url, cid, cc_id, client, locale, skip, top):
        calls.append(skip)
        if skip == 0:
            return {
                "jobRequisitions": [
                    {
                        "itemID": "1",
                        "requisitionTitle": "Platform Engineer",
                        "clientRequisitionID": "REQ-1",
                        "requisitionLocations": [
                            {"nameCode": {"shortName": "Remote, US"}}
                        ],
                        "customFieldGroup": {
                            "stringFields": [
                                {
                                    "nameCode": {"codeValue": "SalaryRange"},
                                    "stringValue": "$100,000 - $130,000",
                                }
                            ]
                        },
                    },
                    {"itemID": "1", "requisitionTitle": "Duplicate"},
                ]
            }
        return {"jobRequisitions": [{"itemID": "2", "requisitionTitle": "SRE"}]}

    monkeypatch.setattr("junior.collectors.session_api._fetch_adp_page", fake_page)
    source_url = "https://workforcenow.adp.com/recruitment.html?cid=C&ccId=CC"
    jobs = ADPCollector().collect(
        _source("adp", source_url=source_url, page_size=2, max_pages=2)
    )

    assert calls == [0, 2]
    assert [job.source_job_id for job in jobs] == ["1", "2"]
    assert jobs[0].location == "Remote, US"
    assert jobs[0].remote_status == "Remote"
    assert jobs[0].salary_text == "$100,000 - $130,000"
    assert "REQ-1" in (jobs[0].description or "")
    assert "jobId=1" in jobs[0].posting_url


def test_adp_requires_identifiers() -> None:
    with pytest.raises(ValueError, match="cid missing"):
        ADPCollector().collect(_source("adp", source_url="https://adp.example/jobs"))


def test_dayforce_sets_up_session_paginates_and_cleans_html(monkeypatch) -> None:
    session = object()
    monkeypatch.setattr(
        "junior.collectors.session_api._start_dayforce_session",
        lambda _url: (session, "token"),
    )
    calls: list[int] = []

    def fake_page(opener, url, token, namespace, board, culture, offset):
        assert opener is session
        assert (token, namespace, board, culture) == (
            "token",
            "acme",
            "candidateportal",
            "en-US",
        )
        calls.append(offset)
        if offset == 0:
            return {
                "maxCount": 2,
                "jobPostings": [
                    {
                        "jobPostingId": 1,
                        "jobTitle": "Remote Engineer",
                        "jobDescription": "<p>Build &amp; operate.</p>",
                        "postingLocations": [],
                        "hasVirtualLocation": True,
                    }
                ],
            }
        return {
            "maxCount": 2,
            "jobPostings": [
                {
                    "jobPostingId": 2,
                    "jobTitle": "Engineer",
                    "postingLocations": [{"formattedAddress": "Boston, MA"}],
                }
            ],
        }

    monkeypatch.setattr(
        "junior.collectors.session_api._fetch_dayforce_page", fake_page
    )
    jobs = DayforceCollector().collect(
        _source(
            "dayforce",
            source_url="https://jobs.dayforcehcm.com/acme/candidateportal",
            page_size=1,
        )
    )

    assert calls == [0, 1]
    assert jobs[0].location == "Remote"
    assert jobs[0].remote_status == "remote"
    assert jobs[0].description == "Build & operate."
    assert jobs[1].location == "Boston, MA"


def test_dayforce_requires_portal_path(monkeypatch) -> None:
    with pytest.raises(ValueError, match="namespace and board"):
        DayforceCollector().collect(
            _source("dayforce", source_url="https://jobs.dayforcehcm.com/")
        )
