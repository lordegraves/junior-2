from datetime import date

from openpyxl import Workbook

from junior.infrastructure.application_database import (
    initialize_database,
    list_applications,
    list_job_history,
)
from junior.infrastructure.history_import import SIMPLE_HEADERS, import_history_workbook


def test_simplified_history_import_is_idempotent_and_syncs_tracker(tmp_path) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Job Log"
    sheet.append(SIMPLE_HEADERS)
    sheet.append(
        (
            "jr-1",
            date(2026, 9, 1),
            "Acme",
            "Platform Engineer",
            "https://job/1",
            "Direct",
            "Applied",
            "Interview",
            "Recruiter",
            "Good fit",
            "Yes",
        )
    )
    sheet.append(
        (None, None, "SkipCo", "Role", None, None, "Skip", None, None, None, "No")
    )
    path = tmp_path / "history.xlsx"
    workbook.save(path)

    first = import_history_workbook(database, path)
    second = import_history_workbook(database, path)

    assert (first.rows_read, first.rows_imported, first.rows_skipped) == (2, 1, 1)
    assert second.rows_imported == 1
    history = list_job_history(database)
    assert len(history) == 1
    assert history[0]["event_date"] == "2026-09-01"
    applications = list_applications(database)
    assert len(applications) == 1
    assert applications[0].job_radar_id == "jr-1"
    assert applications[0].status == "Applied"
