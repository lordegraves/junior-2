from junior.collectors.contracts import CollectorSource
from junior.collectors.schoolspring import SchoolSpringCollector


def test_schoolspring_loads_details_and_falls_back(monkeypatch) -> None:
    def fake_json(url, parameters, headers):
        if url.endswith("GetPagedJobsWithSearch"):
            return {
                "success": True,
                "value": {
                    "jobsList": [
                        {
                            "jobId": 1,
                            "title": "HPC Engineer &amp; Architect",
                            "location": "Boston",
                            "employer": "School",
                        }
                    ]
                },
            }
        return {
            "success": True,
            "value": {
                "jobInfo": {
                    "jobDescription": "Build systems.",
                    "infoURL": "https://school/jobs/1",
                    "applicationDeadline": "Friday",
                },
                "jobLocations": [{"displayLocation": "Boston, MA"}],
                "jobCategories": [
                    {"category": "Technology", "subCategory": "Infrastructure"}
                ],
            },
        }

    monkeypatch.setattr("junior.collectors.schoolspring._get_json", fake_json)
    jobs = SchoolSpringCollector().collect(
        CollectorSource(
            "school",
            "School",
            "schoolspring",
            {"domain_name": "school.schoolspring.com"},
        )
    )
    assert len(jobs) == 1
    assert jobs[0].title == "HPC Engineer & Architect"
    assert jobs[0].location == "Boston, MA"
    assert jobs[0].posting_url == "https://school/jobs/1"
    assert "Employer: School" in (jobs[0].description or "")
    assert "Technology: Infrastructure" in (jobs[0].description or "")
