import hashlib
import sqlite3
from pathlib import Path

import pytest

from junior.application.role_discovery import (
    approved_role_mappings,
    list_role_suggestions,
    record_role_feedback,
    refresh_role_suggestions,
)
from junior.domain.lifecycle import CandidateProfile
from junior.infrastructure.application_database import (
    initialize_database,
    save_candidate_profile,
    save_company,
)


def _profile_with_resume(database: Path, root: Path, profile_id: str) -> None:
    resume = root / f"{profile_id}.txt"
    resume.write_text(
        "Built Linux Kubernetes platforms with Python automation, observability, "
        "networking, infrastructure, deployment, and reliability engineering.",
        encoding="utf-8",
    )
    save_candidate_profile(
        database,
        CandidateProfile(
            profile_id,
            profile_id,
            resume_normalized_text_path=str(resume),
            target_roles=("Infrastructure Engineer",),
        ),
    )


def _posting(database: Path) -> None:
    save_company(
        database,
        company_key="acme",
        name="Acme",
        source_type="greenhouse",
    )
    description = (
        "Build Linux Kubernetes infrastructure using Python automation, "
        "networking, observability, deployment, and reliability practices."
    )
    with sqlite3.connect(database) as connection:
        connection.execute(
            """INSERT INTO job_postings (
                   company_key, source_type, source_url, title, description,
                   canonical_key, content_hash
               ) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                "acme",
                "greenhouse",
                "https://example/jobs/1",
                "Platform Reliability Engineer",
                description,
                "acme:1",
                hashlib.sha256(description.encode()).hexdigest(),
            ),
        )


def test_role_discovery_requires_resume(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    save_candidate_profile(database, CandidateProfile("empty", "Empty"))

    with pytest.raises(ValueError, match="résumé"):
        refresh_role_suggestions(database, "empty")


def test_role_suggestions_require_explicit_profile_owned_approval(
    tmp_path: Path,
) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    _profile_with_resume(database, tmp_path, "first")
    _profile_with_resume(database, tmp_path, "second")
    _posting(database)

    suggestions = refresh_role_suggestions(database, "first")

    assert len(suggestions) == 1
    assert suggestions[0].feedback_state == "pending"
    assert len(suggestions[0].evidence) >= 4
    assert list_role_suggestions(database, "second") == ()
    assert approved_role_mappings(database, "first") == ()

    record_role_feedback(
        database, "first", suggestions[0].suggestion_id, "relevant"
    )

    assert approved_role_mappings(database, "first") == (
        "Platform Reliability Engineer",
    )
    with pytest.raises(ValueError, match="no longer available"):
        record_role_feedback(
            database, "second", suggestions[0].suggestion_id, "relevant"
        )
