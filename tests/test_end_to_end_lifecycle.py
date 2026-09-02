import json
import sqlite3
from dataclasses import replace
from pathlib import Path

from junior.application.review_fixtures import load_review_fixtures
from junior.application.scan_service import ScanService
from junior.collectors.contracts import CollectedJob, CollectorSource
from junior.collectors.registry import CollectorRegistry
from junior.domain.lifecycle import CandidateProfile
from junior.infrastructure.application_database import (
    initialize_database,
    list_applications,
    list_job_evaluations,
    list_jobs,
    save_candidate_profile,
    save_company,
    track_job,
)
from junior.reporting.scan_report import save_report


class LifecycleCollector:
    source_type = "e2e"

    def collect(self, source: CollectorSource) -> tuple[CollectedJob, ...]:
        return (
            CollectedJob(
                "job-1",
                source.company_id,
                "Senior Linux Infrastructure Engineer",
                "Remote",
                "https://example.test/jobs/1",
                "Linux, Kubernetes, Python, automation, and HPC infrastructure.",
                "remote",
                "$170,000 - $210,000",
            ),
        )


def test_clean_install_full_scan_lifecycle(tmp_path: Path) -> None:
    data = tmp_path / "Junior 2.0"
    data.mkdir()
    database = initialize_database(data / "junior-2.sqlite3")
    resume = data / "resume.txt"
    resume.write_text("Linux Kubernetes Python automation HPC", encoding="utf-8")
    save_candidate_profile(
        database,
        CandidateProfile(
            "default",
            "Candidate",
            150_000,
            175_000,
            resume_normalized_text_path=str(resume),
            core_strengths=("Linux", "Kubernetes", "Python", "automation", "HPC"),
        ),
    )
    save_company(database, company_key="acme", name="Acme", source_type="e2e")
    fixture = load_review_fixtures()[1]
    resume_review = replace(fixture, document_kind="resume", company="Resume")

    summary = ScanService(
        database,
        CollectorRegistry({"e2e": LifecycleCollector()}),
        qualification_runner=lambda **_values: fixture,
        resume_runner=lambda **_values: resume_review,
    ).run()

    assert summary.jobs_collected == 1
    assert summary.top_matches == 1
    evaluation = list_job_evaluations(database)[0]
    assert evaluation["recommendation"] == "top_match"
    assert evaluation["location_status"] == "allowed"
    with sqlite3.connect(database) as connection:
        interpretation = connection.execute(
            """SELECT status, shadow_match_json
               FROM job_interpretations"""
        ).fetchone()
    assert interpretation[0] == "validated"
    assert json.loads(interpretation[1])["requirements"]

    job_id = int(list_jobs(database)[0]["id"])
    tracked_id = track_job(database, job_id)
    assert list_applications(database)[0].job_radar_id == tracked_id

    report = save_report(database, data / "scan-report.html")
    content = report.read_text(encoding="utf-8")
    assert "Senior Linux Infrastructure Engineer" in content
    assert "Legacy policy score" in content
