from unittest.mock import patch

from junior.collectors.ashby_workday import AshbyCollector, WorkdayCollector
from junior.collectors.contracts import CollectorSource


def test_ashby_collector_maps_public_job_board_payload() -> None:
    source = CollectorSource(
        "openai", "OpenAI", "ashby", {"source_slug": "openai"}
    )
    payload = {
        "jobs": [
            {
                "id": "job-1",
                "title": "Systems Engineer",
                "jobUrl": "https://jobs.example/job-1",
                "locationName": "Remote",
                "descriptionPlain": "Operate infrastructure.",
                "compensation": {
                    "compensationTierSummary": "$180K - $220K"
                },
            }
        ]
    }

    with patch(
        "junior.collectors.ashby_workday._request_json", return_value=payload
    ):
        jobs = AshbyCollector().collect(source)

    assert jobs[0].source_job_id == "job-1"
    assert jobs[0].description == "Operate infrastructure."
    assert jobs[0].salary_text == "$180K - $220K"


def test_workday_collector_paginates_and_builds_external_url() -> None:
    source = CollectorSource(
        "hpe",
        "HPE",
        "workday",
        {
            "source_url": "https://hpe.example/api/jobs",
            "source_base_url": "https://hpe.example/careers",
            "page_size": 1,
        },
    )
    pages = (
        {
            "total": 2,
            "jobPostings": [
                {
                    "title": "Platform Engineer",
                    "externalPath": "job/one",
                    "bulletFields": ["REQ-1"],
                    "locationsText": "Remote",
                }
            ],
        },
        {
            "total": 2,
            "jobPostings": [
                {
                    "title": "Linux Engineer",
                    "externalPath": "job/two",
                    "jobReqId": "REQ-2",
                }
            ],
        },
    )

    with patch(
        "junior.collectors.ashby_workday._request_json", side_effect=pages
    ) as request:
        jobs = WorkdayCollector().collect(source)

    assert len(jobs) == 2
    assert jobs[0].posting_url == "https://hpe.example/careers/job/one"
    assert request.call_count == 2
