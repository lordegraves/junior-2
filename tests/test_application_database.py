# ruff: noqa: E501
import sqlite3
from pathlib import Path

import pytest

from junior.domain.lifecycle import ApplicationRecord, CandidateProfile
from junior.infrastructure.application_database import (
    LegacyDatabaseError,
    delete_application,
    get_candidate_profile,
    get_company,
    import_legacy_database,
    initialize_database,
    lifecycle_counts,
    list_applications,
    list_companies,
    list_jobs,
    save_application,
    save_candidate_profile,
    save_company,
    set_company_enabled,
    set_job_status,
    track_job,
)


def test_history_records_can_be_edited_excluded_and_deleted(tmp_path: Path) -> None:
    from junior.infrastructure.application_database import (
        delete_history_record,
        get_history_record,
        set_history_included,
        update_history_record,
    )

    database = initialize_database(tmp_path / "junior.sqlite3")
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO job_history (
                   history_type, company, role, import_key
               ) VALUES ('Reviewed', 'Acme', 'Linux Engineer', 'reviewed:acme')"""
        )
    assert set_history_included(database, "reviewed:acme", False)
    assert update_history_record(
        database,
        "reviewed:acme",
        company="Acme Corp",
        role="Infrastructure Engineer",
        status="Reviewed",
        outcome_category="Skipped / Avoid",
        technical_match="Strong",
        primary_blocker="Travel",
        secondary_blocker=None,
        revisit="No",
        notes="Updated",
    )
    record = get_history_record(database, "reviewed:acme")
    assert record["company"] == "Acme Corp"
    assert record["include_in_job_radar"] == 0
    assert delete_history_record(database, "reviewed:acme")
    assert get_history_record(database, "reviewed:acme") is None


def _legacy_database(path: Path) -> None:
    with sqlite3.connect(path) as connection:
        connection.executescript(
            """
            CREATE TABLE companies (
                company_key TEXT PRIMARY KEY, name TEXT NOT NULL, source_type TEXT NOT NULL,
                source_slug TEXT, source_url TEXT, enabled INTEGER, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE job_postings (
                id INTEGER PRIMARY KEY, company_key TEXT, source_type TEXT, source_job_id TEXT,
                source_url TEXT, title TEXT, location TEXT, remote_status TEXT, salary_text TEXT,
                description TEXT, canonical_key TEXT, content_hash TEXT, first_seen_at TEXT,
                last_seen_at TEXT, last_changed_at TEXT, is_active INTEGER, created_at TEXT, updated_at TEXT
            );
            CREATE TABLE scan_runs (
                id INTEGER PRIMARY KEY, generated_at TEXT, started_at TEXT, finished_at TEXT,
                status TEXT, companies_requested INTEGER, companies_scanned INTEGER,
                companies_enabled INTEGER, jobs_found INTEGER, jobs_collected INTEGER,
                actionable_jobs_stored INTEGER, jobs_not_actionable INTEGER, jobs_new INTEGER,
                jobs_seen INTEGER, jobs_changed INTEGER, collector_errors INTEGER,
                errors_count INTEGER, top_matches_count INTEGER, review_needed_count INTEGER
            );
            CREATE TABLE application_tracker (
                job_radar_id TEXT PRIMARY KEY, company_name TEXT, role_title TEXT,
                source_url TEXT, status TEXT, follow_up_on TEXT, outcome TEXT, notes TEXT,
                applied_on TEXT, last_activity_on TEXT, created_at TEXT, updated_at TEXT
            );
            INSERT INTO companies VALUES ('acme', 'Acme', 'greenhouse', NULL, NULL, 1, 'a', 'a');
            INSERT INTO job_postings VALUES (
                1, 'acme', 'greenhouse', '42', 'https://example/jobs/42', 'Platform Engineer',
                'Remote', 'remote', NULL, 'Build systems.', 'acme:42', 'hash', 'a', 'a', NULL, 1, 'a', 'a'
            );
            INSERT INTO scan_runs VALUES (
                1, 'a', 'a', 'a', 'completed', 1, 1, 1, 1, 1, 1, 0, 1, 0, 0, 0, 0, 1, 0
            );
            INSERT INTO application_tracker VALUES (
                'jr-acme-42', 'Acme', 'Platform Engineer', 'https://example/jobs/42',
                'applied', NULL, NULL, 'Promising', '2026-08-01', NULL, 'a', 'a'
            );
            """
        )


def test_initialize_database_creates_lifecycle_tables(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "junior-2.sqlite3")

    counts = lifecycle_counts(database)

    assert database.exists()
    assert set(counts) == {
        "companies",
        "job_postings",
        "job_status",
        "scan_runs",
        "scan_errors",
        "job_seen_events",
        "job_history",
        "application_tracker",
    }


def test_candidate_profile_round_trips(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "junior-2.sqlite3")
    profile = CandidateProfile(
        "default",
        "Clayton Graves",
        compensation_floor_usd=120_000,
        preferred_base_usd=150_000,
        resume_source_path="/private/resume.docx",
        resume_normalized_text_path="/private/resume.txt",
        core_strengths=("Linux", "HPC"),
        credible_adjacent=("Cloud architecture",),
        learning_or_gap=("Rust",),
        avoid=("Commission-only sales",),
    )

    save_candidate_profile(database, profile)

    assert get_candidate_profile(database) == profile


def test_initialize_migrates_existing_candidate_profile_table(tmp_path: Path) -> None:
    database = tmp_path / "junior.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.execute(
            """CREATE TABLE candidate_profiles (
                   profile_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                   compensation_floor_usd INTEGER, preferred_base_usd INTEGER,
                   resume_source_path TEXT, resume_normalized_text_path TEXT,
                   created_at TEXT, updated_at TEXT
               )"""
        )
        connection.execute(
            "INSERT INTO candidate_profiles(profile_id, name) VALUES('default', 'Test')"
        )

    initialize_database(database)

    profile = get_candidate_profile(database)
    assert profile is not None
    assert profile.name == "Test"
    assert profile.core_strengths == ()


def test_import_legacy_database_copies_jobs_scans_and_tracking(tmp_path: Path) -> None:
    source = tmp_path / "junior-1.sqlite3"
    destination = tmp_path / "junior-2.sqlite3"
    _legacy_database(source)

    summary = import_legacy_database(source, destination)

    assert summary.imported is True
    assert dict(summary.table_counts)["job_postings"] == 1
    assert lifecycle_counts(destination)["scan_runs"] == 1
    assert list_applications(destination)[0].status == "applied"


def test_import_is_noop_for_unchanged_source(tmp_path: Path) -> None:
    source = tmp_path / "junior-1.sqlite3"
    destination = tmp_path / "junior-2.sqlite3"
    _legacy_database(source)

    first = import_legacy_database(source, destination)
    second = import_legacy_database(source, destination)

    assert first.imported is True
    assert second.imported is False
    assert lifecycle_counts(destination)["job_postings"] == 1


def test_import_never_accepts_destination_as_source(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")

    with pytest.raises(LegacyDatabaseError, match="different files"):
        import_legacy_database(database, database)


def test_import_rejects_unrelated_sqlite_file(tmp_path: Path) -> None:
    source = tmp_path / "other.sqlite3"
    with sqlite3.connect(source) as connection:
        connection.execute("CREATE TABLE unrelated (id INTEGER)")

    with pytest.raises(LegacyDatabaseError, match="not a Junior 1.x"):
        import_legacy_database(source, tmp_path / "junior-2.sqlite3")


def test_company_sources_can_be_created_updated_and_disabled(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")

    save_company(
        database,
        company_key="acme",
        name="Acme",
        source_type="greenhouse",
        source_url="https://boards.example/acme",
        source_settings={"page_size": 50, "source_base_url": "https://example"},
        notes="Priority target",
    )
    assert set_company_enabled(database, "acme", False) is True

    company = list_companies(database)[0]
    assert company["company_key"] == "acme"
    assert company["enabled"] == 0
    stored = get_company(database, "acme")
    assert stored is not None
    assert stored["source_settings"] == {
        "page_size": 50,
        "source_base_url": "https://example",
    }
    assert stored["notes"] == "Priority target"


def test_job_status_and_tracker_round_trip(tmp_path: Path) -> None:
    source = tmp_path / "junior-1.sqlite3"
    database = tmp_path / "junior-2.sqlite3"
    _legacy_database(source)
    import_legacy_database(source, database)

    assert set_job_status(database, 1, "saved") is True
    assert list_jobs(database)[0]["status"] == "saved"
    tracker_id = track_job(database, 1)

    tracked = next(
        record
        for record in list_applications(database)
        if record.job_radar_id == tracker_id
    )
    save_application(
        database,
        ApplicationRecord(
            tracked.job_radar_id,
            tracked.company_name,
            tracked.role_title,
            tracked.source_url,
            status="interviewing",
            notes="Technical screen",
        ),
    )
    assert (
        next(
            record
            for record in list_applications(database)
            if record.job_radar_id == tracker_id
        ).status
        == "interviewing"
    )
    assert delete_application(database, tracker_id) is True


def test_history_record_can_be_restored_to_tracker(tmp_path: Path) -> None:
    from junior.infrastructure.application_database import restore_history_to_tracker

    database = initialize_database(tmp_path / "junior.sqlite3")
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO job_history (
                   history_type, company, role, source, import_key, notes
               ) VALUES ('Applied', 'Acme', 'Linux Engineer',
                         'https://jobs/acme', 'applied:acme', 'Revisit')"""
        )

    restored_id = restore_history_to_tracker(database, "applied:acme")

    restored = next(
        item for item in list_applications(database) if item.job_radar_id == restored_id
    )
    assert restored.company_name == "Acme"
    assert restored.role_title == "Linux Engineer"
    assert restored.outcome == "Pending / In Progress"
