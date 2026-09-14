import sqlite3
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from junior.application.review_fixtures import load_review_fixtures
from junior.application.scan_service import ScanService
from junior.collectors.contracts import CollectedJob, CollectorSource
from junior.collectors.registry import CollectorRegistry
from junior.domain.lifecycle import CandidateProfile
from junior.infrastructure.application_database import (
    initialize_database,
    lifecycle_counts,
    list_jobs,
    list_scan_runs,
    save_candidate_profile,
    save_company,
)


class StubCollector:
    source_type = "stub"

    def __init__(self) -> None:
        self.title = "Platform Engineer"

    def collect(self, source: CollectorSource) -> tuple[CollectedJob, ...]:
        return (
            CollectedJob(
                "42",
                source.company_id,
                self.title,
                "Remote",
                "https://example/jobs/42",
                "Build reliable systems.",
                "remote",
                "$150K - $190K",
            ),
        )


def test_scan_service_persists_new_seen_and_changed_jobs(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    save_company(
        database,
        company_key="acme",
        name="Acme",
        source_type="stub",
        source_slug="acme",
    )
    collector = StubCollector()
    service = ScanService(database, CollectorRegistry({"stub": collector}))

    first = service.run()
    second = service.run()
    collector.title = "Senior Platform Engineer"
    third = service.run()

    assert (first.jobs_new, first.jobs_changed, first.errors) == (1, 0, 0)
    assert (second.jobs_new, second.jobs_changed) == (0, 0)
    assert (third.jobs_new, third.jobs_changed) == (0, 1)
    assert list_jobs(database)[0]["title"] == "Senior Platform Engineer"
    with sqlite3.connect(database) as connection:
        persisted = connection.execute(
            "SELECT remote_status, salary_text FROM job_postings"
        ).fetchone()
        evaluations = connection.execute(
            "SELECT COUNT(*), MAX(recommendation) FROM job_evaluations"
        ).fetchone()
    assert persisted == ("remote", "$150K - $190K")
    assert evaluations == (3, "review_needed")
    assert len(list_scan_runs(database)) == 3
    assert lifecycle_counts(database)["job_seen_events"] == 3


def test_scan_service_can_target_one_enabled_company(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    for key in ("acme", "other"):
        save_company(database, company_key=key, name=key.title(), source_type="stub")

    summary = ScanService(
        database,
        CollectorRegistry({"stub": StubCollector()}),
        company_keys=("other",),
    ).run()

    assert summary.companies_scanned == 1
    assert list_jobs(database)[0]["company"] == "Other"


def test_scan_service_isolates_collector_errors(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    save_company(
        database,
        company_key="unsupported",
        name="Unsupported",
        source_type="missing",
    )

    summary = ScanService(database, CollectorRegistry({})).run()

    assert summary.errors == 1
    assert list_scan_runs(database)[0]["status"] == "completed_with_errors"
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT COUNT(*) FROM scan_errors").fetchone()[0] == 1


def test_scan_service_persists_validated_llm_interpretations_for_new_jobs(
    tmp_path: Path,
) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    save_company(database, company_key="acme", name="Acme", source_type="stub")
    calls = []

    def interpret(**values):
        calls.append(values)
        return SimpleNamespace(
            section_state="stated",
            validation_state="validated",
            groups=(),
            technical_details=(("Mode", "Two-pass — qwen2.5:3b"),),
        )

    service = ScanService(
        database,
        CollectorRegistry({"stub": StubCollector()}),
        qualification_runner=interpret,
    )
    service.run()
    service.run()

    assert len(calls) == 1
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT model_id, status, section_state FROM job_interpretations"
        ).fetchone()
    assert row == ("qwen2.5:3b", "validated", "stated")


def test_scan_service_records_llm_failure_without_failing_collection(
    tmp_path: Path,
) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    save_company(database, company_key="acme", name="Acme", source_type="stub")

    def fail(**_values):
        raise RuntimeError("model unavailable")

    summary = ScanService(
        database,
        CollectorRegistry({"stub": StubCollector()}),
        qualification_runner=fail,
    ).run()

    assert summary.errors == 0
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT status, error_message FROM job_interpretations"
        ).fetchone()
    assert row == ("failed", "model unavailable")


def test_scan_service_interprets_active_resume_once_per_content_hash(
    tmp_path: Path,
) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    resume = tmp_path / "resume.txt"
    resume.write_text("Linux and Python", encoding="utf-8")
    save_candidate_profile(
        database,
        CandidateProfile(
            "default",
            "Candidate",
            resume_normalized_text_path=str(resume),
        ),
    )
    calls = []

    def interpret_resume(**values):
        calls.append(values)
        return SimpleNamespace(
            section_state="stated",
            validation_state="validated",
            groups=(),
            technical_details=(("Mode", "Resume — qwen2.5:3b"),),
        )

    service = ScanService(
        database,
        CollectorRegistry({}),
        resume_runner=interpret_resume,
    )
    service.run()
    service.run()

    assert len(calls) == 1
    assert calls[0]["content"] == "Linux and Python"
    with sqlite3.connect(database) as connection:
        row = connection.execute(
            "SELECT model_id, status FROM resume_interpretations"
        ).fetchone()
    assert row == ("qwen2.5:3b", "validated")


def test_scan_service_persists_shadow_match_between_validated_artifacts(
    tmp_path: Path,
) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    resume_file = tmp_path / "resume.txt"
    resume_file.write_text("Linux", encoding="utf-8")
    save_candidate_profile(
        database,
        CandidateProfile(
            "default", "Candidate", resume_normalized_text_path=str(resume_file)
        ),
    )
    save_company(database, company_key="acme", name="Acme", source_type="stub")
    job = load_review_fixtures()[1]
    resume = replace(job, document_kind="resume", company="Resume")
    ScanService(
        database,
        CollectorRegistry({"stub": StubCollector()}),
        qualification_runner=lambda **_values: job,
        resume_runner=lambda **_values: resume,
    ).run()

    with sqlite3.connect(database) as connection:
        raw = connection.execute(
            "SELECT shadow_match_json FROM job_interpretations"
        ).fetchone()[0]
    payload = __import__("json").loads(raw)
    assert payload["required_state"] in {"evidenced", "needs_review", "not_found"}
    assert payload["requirements"]
