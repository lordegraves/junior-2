from junior.collectors.contracts import CollectorSource
from junior.collectors.selectminds import SelectMindsCollector


def test_selectminds_extracts_metadata_and_deduplicates(monkeypatch) -> None:
    page = """
    <a href="/jobs/hpc-engineer-7496" class="job_link">HPC Engineer</a>
    <p class="jlr_description">Support HPC users.</p>
    <span class="field_value">106834</span><span>Requisition #</span>
    <span class="field_value">Jun 03, 2026</span><span>Post Date</span>
    <a href="/jobs/hpc-engineer-7496" class="job_link">HPC Engineer</a>
    <span class="field_value">106834</span><span>Requisition #</span>
    """
    monkeypatch.setattr(
        "junior.collectors.selectminds._get_html", lambda _url: page
    )
    jobs = SelectMindsCollector().collect(
        CollectorSource(
            "lab",
            "Lab",
            "selectminds",
            {"source_url": "https://lab.selectminds.com/careers"},
        )
    )
    assert len(jobs) == 1
    assert jobs[0].source_job_id == "106834"
    assert jobs[0].posting_url == "https://lab.selectminds.com/jobs/hpc-engineer-7496"
    assert jobs[0].description == "Support HPC users.\n\nPost Date: Jun 03, 2026"
