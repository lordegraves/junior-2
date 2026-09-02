from junior.collectors.contracts import CollectorSource
from junior.collectors.icims import ICIMSCollector


def test_icims_follows_next_page_and_deduplicates(monkeypatch) -> None:
    pages = [
        """
        <a href="/jobs/168148/data-science/job" title="168148 - Data Scientist"></a>
        <link rel="next" href="/jobs/search?pr=1">
        """,
        """
        <a href="/jobs/168148/data-science/job">Duplicate</a>
        <a href="/jobs/42/platform/job">Platform Engineer</a>
        """,
    ]
    calls = []

    def fake_get(url):
        calls.append(url)
        return pages[len(calls) - 1]

    monkeypatch.setattr("junior.collectors.icims._get_html", fake_get)
    jobs = ICIMSCollector().collect(
        CollectorSource(
            "lab", "Lab", "icims", {"source_url": "https://lab.icims.com/jobs"}
        )
    )
    assert len(calls) == 2
    assert "in_iframe=1" in calls[0]
    assert "pr=1" in calls[1] and "in_iframe=1" in calls[1]
    assert [job.source_job_id for job in jobs] == ["168148", "42"]
    assert jobs[0].title == "Data Scientist"
