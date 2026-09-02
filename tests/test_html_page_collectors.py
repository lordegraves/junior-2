from junior.collectors.contracts import CollectorSource
from junior.collectors.html_pages import HTMLCollector, WekaCollector


def test_html_collector_extracts_locations_ids_and_deduplicates(monkeypatch) -> None:
    page = """
    <a class="jobTitle-link"
       href="/job/Oak-Ridge-Linux-Engineer-TN-37830/123/">Linux Engineer</a>
    <a class="jobTitle-link"
       href="/job/Oak-Ridge-Linux-Engineer-TN-37830/123/">Linux Engineer</a>
    <a class="list-item__link" href="/job-opening/marine-tech/">
      Marine Tech MBARI is hiring
    </a>
    """
    monkeypatch.setattr("junior.collectors.html_pages._get_html", lambda _url: page)
    jobs = HTMLCollector().collect(
        CollectorSource("lab", "Lab", "html", {"source_url": "https://lab/jobs"})
    )
    assert len(jobs) == 2
    assert jobs[0].source_job_id == "123"
    assert jobs[0].location == "Oak Ridge, TN"
    assert jobs[1].title == "Marine Tech"


def test_weka_collector_extracts_cards(monkeypatch) -> None:
    page = """
    <div class="block mrkto-job" data-departments="R&amp;D">
      <a href="?gh_jid=42"></a><h3>AI Engineer</h3>
      <div class="location">U.S. Remote</div><div class="cta-box"></div>
    </div>
    """
    monkeypatch.setattr("junior.collectors.html_pages._get_html", lambda _url: page)
    jobs = WekaCollector().collect(
        CollectorSource(
            "weka", "WEKA", "weka", {"source_url": "https://weka.example/careers/"}
        )
    )
    assert len(jobs) == 1
    assert jobs[0].source_job_id == "42"
    assert jobs[0].location == "U.S. Remote"
    assert jobs[0].description == "R&D"
    assert jobs[0].posting_url.endswith("?gh_jid=42#career-position")
