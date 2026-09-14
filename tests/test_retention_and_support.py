import json
import sqlite3
import zipfile
from pathlib import Path

from junior.domain.lifecycle import CandidateProfile
from junior.infrastructure import diagnostics
from junior.infrastructure.application_database import (
    initialize_database,
    save_candidate_profile,
)
from junior.infrastructure.diagnostics import DiagnosticResult, create_support_bundle
from junior.infrastructure.retention import apply_retention


def test_retention_bounds_internal_reports_and_logs_without_deleting_external(
    tmp_path: Path,
) -> None:
    data = tmp_path / "data"
    logs = data / "logs"
    logs.mkdir(parents=True)
    database = initialize_database(data / "junior.sqlite3")
    internal = [data / f"report-{index}.html" for index in range(3)]
    external = tmp_path / "external-report.html"
    for path in (*internal, external):
        path.write_text("report", encoding="utf-8")
    log_paths = [logs / f"junior-{index}.log" for index in range(3)]
    for path in log_paths:
        path.write_text("log", encoding="utf-8")
        path.touch()
    with sqlite3.connect(database) as connection:
        for path in (*internal, external):
            connection.execute(
                "INSERT INTO report_exports(path, format) VALUES(?, 'html')",
                (str(path),),
            )

    result = apply_retention(
        database, data, report_count=1, log_count=1
    )

    assert result.report_records_removed == 3
    assert result.report_files_removed == 3
    assert result.log_files_removed == 2
    assert external.exists()
    assert sum(path.exists() for path in log_paths) == 1


def test_support_bundle_excludes_resume_content_and_local_resume_paths(
    tmp_path: Path, monkeypatch
) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    resume = tmp_path / "private-resume.txt"
    resume.write_text("PRIVATE RESUME CONTENT", encoding="utf-8")
    save_candidate_profile(
        database,
        CandidateProfile(
            "default",
            "Candidate",
            resume_source_path=str(resume),
            resume_normalized_text_path=str(resume),
            core_strengths=("Linux",),
        ),
    )
    monkeypatch.setattr(
        diagnostics,
        "run_diagnostics",
        lambda *_args, **_kwargs: (DiagnosticResult("Database", True, "ok"),),
    )

    output = create_support_bundle(
        tmp_path / "support.zip", database, tmp_path
    )

    with zipfile.ZipFile(output) as archive:
        payload_text = archive.read("junior-support.json").decode("utf-8")
    payload = json.loads(payload_text)
    assert "PRIVATE RESUME CONTENT" not in payload_text
    assert str(resume) not in payload_text
    assert payload["active_profile_configuration"]["core_strengths"] == ["Linux"]
