from junior.collectors.contracts import CollectorSource
from junior.collectors.jibe import JibeCollector


def test_jibe_paginates_deduplicates_and_preserves_fields(monkeypatch) -> None:
    calls = []

    def fake_json(url, parameters, headers):
        calls.append(parameters["page"])
        identifier = "1" if parameters["page"] == 1 else "2"
        return {
            "jobs": [
                {
                    "data": {
                        "req_id": identifier,
                        "slug": identifier,
                        "title": "GPU Architect",
                        "full_location": "Austin, TX",
                        "description": "Build GPUs.",
                        "responsibilities": "Tune systems.",
                        "tags2": ["$100k"],
                        "tags3": ["$150k"],
                    }
                }
            ],
            "totalCount": 2,
        }

    monkeypatch.setattr("junior.collectors.jibe._get_json", fake_json)
    jobs = JibeCollector().collect(
        CollectorSource(
            "amd",
            "AMD",
            "jibe",
            {
                "source_url": "https://careers.amd.com/api/jobs",
                "job_url_template": "https://careers.amd.com/jobs/{slug}",
                "page_size": 1,
            },
        )
    )

    assert calls == [1, 2]
    assert [job.source_job_id for job in jobs] == ["1", "2"]
    assert jobs[0].location == "Austin, TX"
    assert jobs[0].posting_url == "https://careers.amd.com/jobs/1"
    assert jobs[0].description == "Build GPUs.\n\nTune systems."
    assert jobs[0].salary_text == "$100k | $150k"
