# ruff: noqa: E501
"""Junior 2.0 SQLite lifecycle store and read-only Junior 1.x importer."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path

from junior.application.tracker_workflow import workflow_state
from junior.domain.lifecycle import (
    ApplicationRecord,
    CandidateProfile,
    LegacyImportSummary,
)
from junior.scoring.history_match import HistoryRecord

_LEGACY_TABLES = (
    "companies",
    "job_postings",
    "job_status",
    "scan_runs",
    "scan_errors",
    "job_seen_events",
    "job_history",
    "application_tracker",
)

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS legacy_imports (
    source_fingerprint TEXT PRIMARY KEY,
    source_path TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS candidate_profiles (
    profile_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    compensation_floor_usd INTEGER,
    preferred_base_usd INTEGER,
    resume_source_path TEXT,
    resume_normalized_text_path TEXT,
    core_strengths_json TEXT NOT NULL DEFAULT '[]',
    credible_adjacent_json TEXT NOT NULL DEFAULT '[]',
    learning_or_gap_json TEXT NOT NULL DEFAULT '[]',
    avoid_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS companies (
    company_key TEXT PRIMARY KEY, name TEXT NOT NULL, source_type TEXT NOT NULL,
    source_slug TEXT, source_url TEXT, enabled INTEGER NOT NULL DEFAULT 1,
    source_settings_json TEXT NOT NULL DEFAULT '{}', notes TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_postings (
    id INTEGER PRIMARY KEY AUTOINCREMENT, company_key TEXT NOT NULL,
    source_type TEXT NOT NULL, source_job_id TEXT, source_url TEXT NOT NULL,
    title TEXT NOT NULL, location TEXT, remote_status TEXT, salary_text TEXT,
    description TEXT, canonical_key TEXT NOT NULL, content_hash TEXT NOT NULL,
    first_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, last_changed_at TEXT,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_status (
    job_posting_id INTEGER PRIMARY KEY, status TEXT NOT NULL DEFAULT 'new',
    user_notes TEXT, applied_at TEXT, rejected_at TEXT, archived_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_evaluations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_posting_id INTEGER NOT NULL, scan_run_id INTEGER NOT NULL,
    score INTEGER NOT NULL, policy_score INTEGER NOT NULL DEFAULT 0,
    location_status TEXT NOT NULL DEFAULT 'unknown', recommendation TEXT NOT NULL,
    recommended_action TEXT NOT NULL DEFAULT 'hold',
    hiring_probability TEXT NOT NULL DEFAULT 'Unknown',
    risk_flags_json TEXT NOT NULL DEFAULT '[]',
    compensation_label TEXT NOT NULL, compensation_range TEXT NOT NULL,
    resume_match_label TEXT NOT NULL,
    evidence_json TEXT NOT NULL DEFAULT '[]', gaps_json TEXT NOT NULL DEFAULT '[]',
    reasons_json TEXT NOT NULL DEFAULT '[]',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_posting_id, scan_run_id)
);

CREATE TABLE IF NOT EXISTS job_interpretations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_posting_id INTEGER NOT NULL, scan_run_id INTEGER NOT NULL,
    model_id TEXT, status TEXT NOT NULL,
    section_state TEXT, interpretation_json TEXT,
    shadow_match_json TEXT,
    error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(job_posting_id, scan_run_id)
);

CREATE TABLE IF NOT EXISTS resume_interpretations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL, content_hash TEXT NOT NULL,
    model_id TEXT, status TEXT NOT NULL,
    interpretation_json TEXT, error_message TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(profile_id, content_hash)
);

CREATE TABLE IF NOT EXISTS report_exports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL, format TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS scan_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, finished_at TEXT,
    status TEXT NOT NULL DEFAULT 'completed', companies_requested INTEGER NOT NULL DEFAULT 0,
    companies_scanned INTEGER NOT NULL DEFAULT 0, companies_enabled INTEGER NOT NULL DEFAULT 0,
    jobs_found INTEGER NOT NULL DEFAULT 0, jobs_collected INTEGER NOT NULL DEFAULT 0,
    actionable_jobs_stored INTEGER NOT NULL DEFAULT 0, jobs_not_actionable INTEGER NOT NULL DEFAULT 0,
    jobs_new INTEGER NOT NULL DEFAULT 0, jobs_seen INTEGER NOT NULL DEFAULT 0,
    jobs_changed INTEGER NOT NULL DEFAULT 0, collector_errors INTEGER NOT NULL DEFAULT 0,
    errors_count INTEGER NOT NULL DEFAULT 0, top_matches_count INTEGER NOT NULL DEFAULT 0,
    review_needed_count INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS scan_errors (
    id INTEGER PRIMARY KEY AUTOINCREMENT, scan_run_id INTEGER, company_key TEXT,
    source_type TEXT, error_type TEXT NOT NULL, error_message TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_seen_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT, job_posting_id INTEGER, scan_run_id INTEGER,
    event_type TEXT NOT NULL, event_details TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT, history_type TEXT NOT NULL,
    company TEXT NOT NULL, role TEXT NOT NULL, source TEXT, ats_platform TEXT,
    work_arrangement TEXT, location TEXT, comp_range TEXT, event_date TEXT,
    status TEXT, outcome_category TEXT, recruiter_contact TEXT, technical_match TEXT,
    hiring_probability TEXT, skills_signals TEXT, primary_blocker TEXT,
    secondary_blocker TEXT, revisit TEXT, include_in_job_radar INTEGER NOT NULL DEFAULT 1,
    import_key TEXT NOT NULL UNIQUE, notes TEXT, applied_on TEXT,
    last_activity_on TEXT, follow_up_on TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS application_tracker (
    job_radar_id TEXT PRIMARY KEY, company_name TEXT NOT NULL, role_title TEXT NOT NULL,
    source_url TEXT, status TEXT NOT NULL DEFAULT 'review_needed', follow_up_on TEXT,
    outcome TEXT, notes TEXT, applied_on TEXT, last_activity_on TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_job_postings_company_key ON job_postings(company_key);
CREATE INDEX IF NOT EXISTS idx_job_postings_source_url ON job_postings(source_url);
CREATE INDEX IF NOT EXISTS idx_job_evaluations_run ON job_evaluations(scan_run_id);
CREATE INDEX IF NOT EXISTS idx_job_interpretations_run ON job_interpretations(scan_run_id);
CREATE INDEX IF NOT EXISTS idx_application_tracker_status ON application_tracker(status);
CREATE INDEX IF NOT EXISTS idx_application_tracker_follow_up ON application_tracker(follow_up_on);
"""


class LegacyDatabaseError(ValueError):
    """The selected database is not a readable Junior 1.x database."""


def initialize_database(database_path: str | Path) -> Path:
    path = Path(database_path).expanduser().resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as connection:
        connection.executescript(SCHEMA_SQL)
        _migrate_candidate_profile_columns(connection)
        _migrate_company_columns(connection)
        _migrate_interpretation_columns(connection)
        _migrate_evaluation_columns(connection)
        connection.execute(
            "INSERT OR REPLACE INTO schema_metadata(key, value) VALUES('schema_version', '2')"
        )
    return path


def import_legacy_database(
    source_path: str | Path,
    destination_path: str | Path,
) -> LegacyImportSummary:
    """Copy compatible 1.x rows without ever opening the source for writing."""

    source = Path(source_path).expanduser().resolve()
    destination = initialize_database(destination_path)
    if not source.is_file():
        raise LegacyDatabaseError("Select an existing Junior 1.x SQLite database.")
    if source == destination:
        raise LegacyDatabaseError(
            "The 1.x source and 2.0 destination must be different files."
        )

    fingerprint = _fingerprint(source)
    source_uri = f"file:{source.as_posix()}?mode=ro"
    try:
        legacy = sqlite3.connect(source_uri, uri=True)
    except sqlite3.Error as error:
        raise LegacyDatabaseError(
            "Junior could not open that database read-only."
        ) from error

    try:
        source_tables = _table_names(legacy)
        if "job_postings" not in source_tables or "scan_runs" not in source_tables:
            raise LegacyDatabaseError("The selected file is not a Junior 1.x database.")

        with sqlite3.connect(destination) as target:
            previous = target.execute(
                "SELECT 1 FROM legacy_imports WHERE source_fingerprint = ?",
                (fingerprint,),
            ).fetchone()
            if previous is not None:
                return LegacyImportSummary(str(source), False, ())

            counts: list[tuple[str, int]] = []
            target.execute("BEGIN IMMEDIATE")
            for table in _LEGACY_TABLES:
                if table not in source_tables:
                    continue
                count = _copy_table(legacy, target, table)
                counts.append((table, count))
            target.execute(
                "INSERT INTO legacy_imports(source_fingerprint, source_path) VALUES(?, ?)",
                (fingerprint, str(source)),
            )
        return LegacyImportSummary(str(source), True, tuple(counts))
    except sqlite3.Error as error:
        raise LegacyDatabaseError(
            "Junior could not import the legacy database safely."
        ) from error
    finally:
        legacy.close()


def list_applications(database_path: str | Path) -> tuple[ApplicationRecord, ...]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute(
            """SELECT job_radar_id, company_name, role_title, source_url, status,
                      follow_up_on, outcome, notes, applied_on, last_activity_on
               FROM application_tracker
               ORDER BY updated_at DESC, company_name, role_title"""
        ).fetchall()
    return tuple(ApplicationRecord(**dict(row)) for row in rows)


def get_candidate_profile(
    database_path: str | Path, profile_id: str = "default"
) -> CandidateProfile | None:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """SELECT profile_id, name, compensation_floor_usd,
                      preferred_base_usd, resume_source_path,
                      resume_normalized_text_path, core_strengths_json,
                      credible_adjacent_json, learning_or_gap_json, avoid_json
               FROM candidate_profiles WHERE profile_id = ?""",
            (profile_id,),
        ).fetchone()
    if row is None:
        return None
    values = dict(row)
    return CandidateProfile(
        profile_id=values["profile_id"],
        name=values["name"],
        compensation_floor_usd=values["compensation_floor_usd"],
        preferred_base_usd=values["preferred_base_usd"],
        resume_source_path=values["resume_source_path"],
        resume_normalized_text_path=values["resume_normalized_text_path"],
        core_strengths=_decode_string_list(values["core_strengths_json"]),
        credible_adjacent=_decode_string_list(values["credible_adjacent_json"]),
        learning_or_gap=_decode_string_list(values["learning_or_gap_json"]),
        avoid=_decode_string_list(values["avoid_json"]),
    )


def save_candidate_profile(
    database_path: str | Path, profile: CandidateProfile
) -> None:
    if not profile.name.strip():
        raise ValueError("Profile name is required.")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """INSERT INTO candidate_profiles (
                   profile_id, name, compensation_floor_usd, preferred_base_usd,
                   resume_source_path, resume_normalized_text_path,
                   core_strengths_json, credible_adjacent_json,
                   learning_or_gap_json, avoid_json
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(profile_id) DO UPDATE SET
                   name = excluded.name,
                   compensation_floor_usd = excluded.compensation_floor_usd,
                   preferred_base_usd = excluded.preferred_base_usd,
                   resume_source_path = excluded.resume_source_path,
                   resume_normalized_text_path = excluded.resume_normalized_text_path,
                   core_strengths_json = excluded.core_strengths_json,
                   credible_adjacent_json = excluded.credible_adjacent_json,
                   learning_or_gap_json = excluded.learning_or_gap_json,
                   avoid_json = excluded.avoid_json,
                   updated_at = CURRENT_TIMESTAMP""",
            (
                profile.profile_id,
                profile.name.strip(),
                profile.compensation_floor_usd,
                profile.preferred_base_usd,
                profile.resume_source_path,
                profile.resume_normalized_text_path,
                _encode_string_list(profile.core_strengths),
                _encode_string_list(profile.credible_adjacent),
                _encode_string_list(profile.learning_or_gap),
                _encode_string_list(profile.avoid),
            ),
        )


def _migrate_candidate_profile_columns(connection: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(candidate_profiles)"
        ).fetchall()
    }
    for column in (
        "core_strengths_json",
        "credible_adjacent_json",
        "learning_or_gap_json",
        "avoid_json",
    ):
        if column not in existing:
            connection.execute(
                f"ALTER TABLE candidate_profiles ADD COLUMN {column} "
                "TEXT NOT NULL DEFAULT '[]'"
            )


def _encode_string_list(values: tuple[str, ...]) -> str:
    cleaned = tuple(value.strip() for value in values if value.strip())
    return json.dumps(cleaned)


def _decode_string_list(value: str) -> tuple[str, ...]:
    decoded = json.loads(value or "[]")
    if not isinstance(decoded, list):
        return ()
    return tuple(str(item).strip() for item in decoded if str(item).strip())


def lifecycle_counts(database_path: str | Path) -> dict[str, int]:
    with sqlite3.connect(database_path) as connection:
        return {
            table: int(
                connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
            )
            for table in _LEGACY_TABLES
        }


def application_workflow_counts(database_path: str | Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    for application in list_applications(database_path):
        state = workflow_state(application)
        counts[state] = counts.get(state, 0) + 1
    return counts


def list_application_views(database_path: str | Path) -> tuple[dict[str, object], ...]:
    rows = []
    for application in list_applications(database_path):
        row = vars(application).copy()
        row["workflow_state"] = workflow_state(application)
        rows.append(row)
    return tuple(rows)


def list_companies(database_path: str | Path) -> tuple[dict[str, object], ...]:
    return _query_rows(
        database_path,
        """SELECT company_key, name, source_type,
                  COALESCE(source_slug, source_url, '') AS source,
                  enabled, updated_at
           FROM companies ORDER BY enabled DESC, name""",
    )


def list_job_history(database_path: str | Path) -> tuple[dict[str, object], ...]:
    return _query_rows(
        database_path,
        """SELECT import_key, history_type, company, role, status,
                  outcome_category, event_date, primary_blocker, revisit,
                  include_in_job_radar
           FROM job_history ORDER BY COALESCE(event_date, imported_at) DESC,
                  company, role""",
    )


def set_history_included(
    database_path: str | Path, import_key: str, included: bool
) -> bool:
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """UPDATE job_history
               SET include_in_job_radar = ?, updated_at = CURRENT_TIMESTAMP
               WHERE import_key = ?""",
            (int(included), import_key),
        )
    return cursor.rowcount > 0


def get_history_record(
    database_path: str | Path, import_key: str
) -> dict[str, object] | None:
    rows = _query_rows(
        database_path,
        """SELECT import_key, company, role, status, outcome_category,
                  technical_match, primary_blocker, secondary_blocker,
                  revisit, notes, include_in_job_radar
           FROM job_history WHERE import_key = ?""",
        (import_key,),
    )
    return rows[0] if rows else None


def update_history_record(
    database_path: str | Path,
    import_key: str,
    *,
    company: str,
    role: str,
    status: str | None,
    outcome_category: str | None,
    technical_match: str | None,
    primary_blocker: str | None,
    secondary_blocker: str | None,
    revisit: str | None,
    notes: str | None,
) -> bool:
    if not company.strip() or not role.strip():
        raise ValueError("History company and role are required.")
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """UPDATE job_history SET
                   company = ?, role = ?, status = ?, outcome_category = ?,
                   technical_match = ?, primary_blocker = ?, secondary_blocker = ?,
                   revisit = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
               WHERE import_key = ?""",
            (
                company.strip(),
                role.strip(),
                status,
                outcome_category,
                technical_match,
                primary_blocker,
                secondary_blocker,
                revisit,
                notes,
                import_key,
            ),
        )
    return cursor.rowcount > 0


def delete_history_record(database_path: str | Path, import_key: str) -> bool:
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM job_history WHERE import_key = ?", (import_key,)
        )
    return cursor.rowcount > 0


def restore_history_to_tracker(database_path: str | Path, import_key: str) -> str:
    rows = _query_rows(
        database_path,
        """SELECT import_key, company, role, source, notes, applied_on,
                  last_activity_on, follow_up_on
           FROM job_history WHERE import_key = ?""",
        (import_key,),
    )
    if not rows:
        raise ValueError("The history record no longer exists.")
    row = rows[0]

    def optional(value: object) -> str | None:
        return str(value) if value is not None else None

    application_id = f"history-{str(row['import_key'])}"
    save_application(
        database_path,
        ApplicationRecord(
            application_id,
            str(row["company"]),
            str(row["role"]),
            optional(row["source"]),
            "applied",
            optional(row["follow_up_on"]),
            "Pending / In Progress",
            optional(row["notes"]),
            optional(row["applied_on"]),
            optional(row["last_activity_on"]),
        ),
    )
    return application_id


def list_history_records(database_path: str | Path) -> tuple[HistoryRecord, ...]:
    rows = _query_rows(
        database_path,
        """SELECT import_key, company, role, status, outcome_category,
                  technical_match, primary_blocker, include_in_job_radar
           FROM job_history WHERE include_in_job_radar = 1
           ORDER BY COALESCE(event_date, imported_at) DESC, id DESC""",
    )
    return tuple(
        HistoryRecord(
            import_key=str(row["import_key"]),
            company=str(row["company"]),
            role=str(row["role"]),
            status=str(row["status"]) if row["status"] is not None else None,
            outcome_category=(
                str(row["outcome_category"])
                if row["outcome_category"] is not None
                else None
            ),
            technical_match=(
                str(row["technical_match"])
                if row["technical_match"] is not None
                else None
            ),
            primary_blocker=(
                str(row["primary_blocker"])
                if row["primary_blocker"] is not None
                else None
            ),
            include_in_job_radar=bool(row["include_in_job_radar"]),
        )
        for row in rows
    )


def list_job_evaluations(
    database_path: str | Path,
) -> tuple[dict[str, object], ...]:
    return _query_rows(
        database_path,
        """SELECT e.id, p.company_key, p.title, e.score, e.policy_score,
                  e.location_status, e.recommendation, e.recommended_action,
                  e.hiring_probability,
                  e.compensation_label, e.resume_match_label,
                  e.reasons_json, e.created_at
           FROM job_evaluations e
           JOIN job_postings p ON p.id = e.job_posting_id
           ORDER BY e.created_at DESC, e.score DESC""",
    )


def list_report_exports(database_path: str | Path) -> tuple[dict[str, object], ...]:
    return _query_rows(
        database_path,
        """SELECT id, path, format, created_at
           FROM report_exports ORDER BY created_at DESC, id DESC""",
    )


def get_company(
    database_path: str | Path, company_key: str
) -> dict[str, object] | None:
    rows = _query_rows(
        database_path,
        """SELECT company_key, name, source_type, source_slug, source_url,
                  enabled, source_settings_json, notes
           FROM companies WHERE company_key = ?""",
        (company_key,),
    )
    if not rows:
        return None
    row = rows[0]
    row["source_settings"] = json.loads(str(row.pop("source_settings_json") or "{}"))
    return row


def save_company(
    database_path: str | Path,
    *,
    company_key: str,
    name: str,
    source_type: str,
    source_url: str | None = None,
    source_slug: str | None = None,
    enabled: bool = True,
    source_settings: dict[str, object] | None = None,
    notes: str | None = None,
) -> None:
    """Create or update a company source used by native scans."""

    values = {
        "company key": company_key.strip(),
        "company name": name.strip(),
        "source type": source_type.strip(),
    }
    for label, value in values.items():
        if not value:
            raise ValueError(f"{label.title()} is required.")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """INSERT INTO companies (
                   company_key, name, source_type, source_slug, source_url, enabled,
                   source_settings_json, notes
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(company_key) DO UPDATE SET
                   name = excluded.name,
                   source_type = excluded.source_type,
                   source_slug = excluded.source_slug,
                   source_url = excluded.source_url,
                   enabled = excluded.enabled,
                   source_settings_json = excluded.source_settings_json,
                   notes = excluded.notes,
                   updated_at = CURRENT_TIMESTAMP""",
            (
                values["company key"],
                values["company name"],
                values["source type"],
                source_slug.strip() if source_slug else None,
                source_url.strip() if source_url else None,
                int(enabled),
                json.dumps(source_settings or {}, sort_keys=True),
                notes.strip() if notes else None,
            ),
        )


def _migrate_company_columns(connection: sqlite3.Connection) -> None:
    existing = {
        row[1] for row in connection.execute("PRAGMA table_info(companies)").fetchall()
    }
    if "source_settings_json" not in existing:
        connection.execute(
            "ALTER TABLE companies ADD COLUMN source_settings_json "
            "TEXT NOT NULL DEFAULT '{}'"
        )
    if "notes" not in existing:
        connection.execute("ALTER TABLE companies ADD COLUMN notes TEXT")


def _migrate_interpretation_columns(connection: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in connection.execute(
            "PRAGMA table_info(job_interpretations)"
        ).fetchall()
    }
    if "shadow_match_json" not in existing:
        connection.execute(
            "ALTER TABLE job_interpretations ADD COLUMN shadow_match_json TEXT"
        )


def _migrate_evaluation_columns(connection: sqlite3.Connection) -> None:
    existing = {
        row[1]
        for row in connection.execute("PRAGMA table_info(job_evaluations)").fetchall()
    }
    if "policy_score" not in existing:
        connection.execute(
            "ALTER TABLE job_evaluations ADD COLUMN policy_score "
            "INTEGER NOT NULL DEFAULT 0"
        )
    if "location_status" not in existing:
        connection.execute(
            "ALTER TABLE job_evaluations ADD COLUMN location_status "
            "TEXT NOT NULL DEFAULT 'unknown'"
        )
    if "recommended_action" not in existing:
        connection.execute(
            "ALTER TABLE job_evaluations ADD COLUMN recommended_action "
            "TEXT NOT NULL DEFAULT 'hold'"
        )
    if "hiring_probability" not in existing:
        connection.execute(
            "ALTER TABLE job_evaluations ADD COLUMN hiring_probability "
            "TEXT NOT NULL DEFAULT 'Unknown'"
        )
    if "risk_flags_json" not in existing:
        connection.execute(
            "ALTER TABLE job_evaluations ADD COLUMN risk_flags_json "
            "TEXT NOT NULL DEFAULT '[]'"
        )


def set_company_enabled(
    database_path: str | Path, company_key: str, enabled: bool
) -> bool:
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            """UPDATE companies SET enabled = ?, updated_at = CURRENT_TIMESTAMP
               WHERE company_key = ?""",
            (int(enabled), company_key),
        )
    return cursor.rowcount > 0


def list_jobs(database_path: str | Path) -> tuple[dict[str, object], ...]:
    return _query_rows(
        database_path,
        """SELECT job_postings.id, companies.name AS company, job_postings.title,
                  job_postings.location, job_postings.remote_status,
                  COALESCE(job_status.status, 'new') AS status,
                  job_postings.last_seen_at
           FROM job_postings
           LEFT JOIN companies ON companies.company_key = job_postings.company_key
           LEFT JOIN job_status ON job_status.job_posting_id = job_postings.id
           ORDER BY job_postings.last_seen_at DESC, company, job_postings.title""",
    )


def get_job(database_path: str | Path, job_posting_id: int) -> dict[str, object] | None:
    rows = _query_rows(
        database_path,
        """SELECT job_postings.id, companies.name AS company, job_postings.title,
                  job_postings.description, job_postings.source_url
           FROM job_postings
           LEFT JOIN companies ON companies.company_key = job_postings.company_key
           WHERE job_postings.id = ?""",
        (job_posting_id,),
    )
    return rows[0] if rows else None


def set_job_status(
    database_path: str | Path,
    job_posting_id: int,
    status: str,
    notes: str | None = None,
) -> bool:
    clean_status = status.strip().lower().replace(" ", "_")
    if not clean_status:
        raise ValueError("Job status is required.")
    with sqlite3.connect(database_path) as connection:
        exists = connection.execute(
            "SELECT 1 FROM job_postings WHERE id = ?", (job_posting_id,)
        ).fetchone()
        if exists is None:
            return False
        connection.execute(
            """INSERT INTO job_status (job_posting_id, status, user_notes)
               VALUES (?, ?, ?)
               ON CONFLICT(job_posting_id) DO UPDATE SET
                   status = excluded.status,
                   user_notes = excluded.user_notes,
                   updated_at = CURRENT_TIMESTAMP""",
            (job_posting_id, clean_status, notes),
        )
    return True


def track_job(database_path: str | Path, job_posting_id: int) -> str:
    """Add a discovered job to the application tracker without duplication."""

    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            """SELECT job_postings.company_key, companies.name AS company_name,
                      job_postings.title, job_postings.source_url,
                      job_postings.source_job_id, job_postings.canonical_key
               FROM job_postings
               LEFT JOIN companies
                 ON companies.company_key = job_postings.company_key
               WHERE job_postings.id = ?""",
            (job_posting_id,),
        ).fetchone()
        if row is None:
            raise ValueError("The selected job no longer exists.")
        token = row["source_job_id"] or row["canonical_key"]
        job_radar_id = f"jr-{row['company_key']}-{token}"
        connection.execute(
            """INSERT INTO application_tracker (
                   job_radar_id, company_name, role_title, source_url
               ) VALUES (?, ?, ?, ?)
               ON CONFLICT(job_radar_id) DO NOTHING""",
            (job_radar_id, row["company_name"], row["title"], row["source_url"]),
        )
    return job_radar_id


def save_application(database_path: str | Path, application: ApplicationRecord) -> None:
    if not application.job_radar_id.strip():
        raise ValueError("Application ID is required.")
    if not application.company_name.strip() or not application.role_title.strip():
        raise ValueError("Company and role are required.")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """INSERT INTO application_tracker (
                   job_radar_id, company_name, role_title, source_url, status,
                   follow_up_on, outcome, notes, applied_on, last_activity_on
               ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(job_radar_id) DO UPDATE SET
                   company_name = excluded.company_name,
                   role_title = excluded.role_title,
                   source_url = excluded.source_url,
                   status = excluded.status,
                   follow_up_on = excluded.follow_up_on,
                   outcome = excluded.outcome,
                   notes = excluded.notes,
                   applied_on = excluded.applied_on,
                   last_activity_on = excluded.last_activity_on,
                   updated_at = CURRENT_TIMESTAMP""",
            (
                application.job_radar_id.strip(),
                application.company_name.strip(),
                application.role_title.strip(),
                application.source_url,
                application.status.strip().lower().replace(" ", "_"),
                application.follow_up_on,
                application.outcome,
                application.notes,
                application.applied_on,
                application.last_activity_on,
            ),
        )


def delete_application(database_path: str | Path, job_radar_id: str) -> bool:
    with sqlite3.connect(database_path) as connection:
        cursor = connection.execute(
            "DELETE FROM application_tracker WHERE job_radar_id = ?",
            (job_radar_id,),
        )
    return cursor.rowcount > 0


def list_scan_runs(database_path: str | Path) -> tuple[dict[str, object], ...]:
    return _query_rows(
        database_path,
        """SELECT id, generated_at, status, companies_scanned, jobs_collected,
                  jobs_new, jobs_changed, collector_errors,
                  review_needed_count
           FROM scan_runs ORDER BY generated_at DESC, id DESC""",
    )


def _query_rows(
    database_path: str | Path,
    statement: str,
    parameters: tuple[object, ...] = (),
) -> tuple[dict[str, object], ...]:
    with sqlite3.connect(database_path) as connection:
        connection.row_factory = sqlite3.Row
        return tuple(
            dict(row) for row in connection.execute(statement, parameters).fetchall()
        )


def _fingerprint(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _table_names(connection: sqlite3.Connection) -> set[str]:
    return {
        str(row[0])
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )
    }


def _columns(connection: sqlite3.Connection, table: str) -> tuple[str, ...]:
    return tuple(
        str(row[1]) for row in connection.execute(f'PRAGMA table_info("{table}")')
    )


def _copy_table(
    source: sqlite3.Connection,
    target: sqlite3.Connection,
    table: str,
) -> int:
    shared = tuple(
        column
        for column in _columns(source, table)
        if column in _columns(target, table)
    )
    if not shared:
        return 0
    quoted = ", ".join(f'"{column}"' for column in shared)
    placeholders = ", ".join("?" for _ in shared)
    rows = source.execute(f'SELECT {quoted} FROM "{table}"').fetchall()
    target.executemany(
        f'INSERT OR REPLACE INTO "{table}" ({quoted}) VALUES ({placeholders})',
        rows,
    )
    return len(rows)
