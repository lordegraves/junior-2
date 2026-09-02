from junior.collectors.contracts import CollectorSource
from junior.collectors.enterprise_api import JobSynCollector, OracleHCMCollector


def _source(source_type: str, **settings: object) -> CollectorSource:
    return CollectorSource("acme", "Acme", source_type, settings)


def test_oracle_hcm_paginates_and_preserves_fields(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_json(url, parameters, headers):
        calls.append(parameters)
        return {
            "items": [
                {
                    "TotalJobsCount": 2,
                    "requisitionList": [
                        {
                            "Id": str(len(calls)),
                            "Title": "Engineer",
                            "PrimaryLocation": "Boston, MA",
                            "ShortDescriptionStr": "Build systems.",
                            "ExternalQualificationsStr": "Python",
                            "WorkplaceType": "Hybrid",
                        }
                    ],
                }
            ]
        }

    monkeypatch.setattr("junior.collectors.enterprise_api._get_json", fake_json)
    jobs = OracleHCMCollector().collect(
        _source(
            "oracle_hcm",
            source_url="https://acme.oraclecloud.com/api",
            referer_url="https://acme.oraclecloud.com/sites/jobs",
            page_size=1,
        )
    )

    assert len(jobs) == 2
    assert calls[1]["finder"].endswith("offset=1")
    assert jobs[0].posting_url.endswith("/sites/jobs/job/1")
    assert jobs[0].description == "Build systems.\n\nPython"
    assert jobs[0].remote_status == "Hybrid"


def test_jobsyn_combines_featured_jobs_and_paginates(monkeypatch) -> None:
    calls: list[dict] = []

    def fake_json(url, parameters, headers):
        calls.append(parameters)
        if parameters["page"] == 1:
            return {
                "featured_jobs": [
                    {
                        "reqid": "1",
                        "title_exact": "Engineer",
                        "city_exact": "Boston",
                        "state_short_exact": "MA",
                    }
                ],
                "jobs": [{"reqid": "1", "title": "Duplicate"}],
                "pagination": {"has_more_pages": True, "total_pages": 2},
            }
        return {
            "jobs": [{"reqid": "2", "title": "Architect", "job_url": "https://job/2"}],
            "pagination": {"has_more_pages": False},
        }

    monkeypatch.setattr("junior.collectors.enterprise_api._get_json", fake_json)
    jobs = JobSynCollector().collect(
        _source(
            "jobsyn",
            source_url="https://api.jobsyn.com/jobs",
            referer_url="https://acme.jobs/jobs/",
        )
    )

    assert [job.source_job_id for job in jobs] == ["1", "2"]
    assert jobs[0].location == "Boston, MA"
    assert jobs[0].posting_url.endswith("?q=1")
    assert jobs[1].posting_url == "https://job/2"
