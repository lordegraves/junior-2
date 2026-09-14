"""Apply bounded report and dated-log retention without touching external exports."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RetentionResult:
    report_records_removed: int
    report_files_removed: int
    log_files_removed: int


def apply_retention(
    database_path: str | Path,
    data_directory: str | Path,
    *,
    report_count: int | None,
    log_count: int | None,
) -> RetentionResult:
    root = Path(data_directory).expanduser().resolve()
    report_records_removed = 0
    report_files_removed = 0
    if report_count is not None:
        with sqlite3.connect(database_path) as connection:
            rows = connection.execute(
                "SELECT id, path FROM report_exports ORDER BY id DESC"
            ).fetchall()
            for report_id, raw_path in rows[report_count:]:
                path = Path(raw_path).expanduser().resolve()
                if path.is_relative_to(root) and path.is_file():
                    path.unlink()
                    report_files_removed += 1
                connection.execute(
                    "DELETE FROM report_exports WHERE id = ?", (report_id,)
                )
                report_records_removed += 1
    log_files_removed = 0
    if log_count is not None:
        log_directory = root / "logs"
        logs = sorted(
            (path for path in log_directory.glob("*") if path.is_file()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for path in logs[log_count:]:
            path.unlink()
            log_files_removed += 1
    return RetentionResult(
        report_records_removed, report_files_removed, log_files_removed
    )
