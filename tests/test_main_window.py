import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow

from junior.desktop.main_window import (
    ApplicationEditorDialog,
    CompanyEditorDialog,
    JuniorMainWindow,
    ProfilePage,
)
from junior.domain.lifecycle import ApplicationRecord
from junior.infrastructure.application_database import (
    get_candidate_profile,
    initialize_database,
)


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_default_window_is_application_shell_not_workbench(tmp_path: Path) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")

    window = JuniorMainWindow(database, tmp_path)

    assert window.windowTitle() == "Junior 2.0"
    assert [window.navigation.item(row).text() for row in range(9)] == [
        "Home",
        "Profile",
        "Companies",
        "Scans",
        "Jobs",
        "Applications",
        "History",
        "Reports",
        "Settings",
    ]
    window.close()


def test_profile_page_persists_candidate_preferences(tmp_path: Path) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    page = ProfilePage(database, tmp_path)
    page.name_input.setText("Clayton Graves")
    page.floor_input.setValue(120_000)
    page.preferred_input.setValue(150_000)
    page.core_strengths_input.setPlainText("Linux\nHPC\n")
    page.adjacent_input.setPlainText("Cloud architecture")
    page.gaps_input.setPlainText("Rust")
    page.avoid_input.setPlainText("Commission-only sales")

    page._save()

    profile = get_candidate_profile(database)
    assert profile is not None
    assert profile.name == "Clayton Graves"
    assert profile.compensation_floor_usd == 120_000
    assert profile.preferred_base_usd == 150_000
    assert profile.core_strengths == ("Linux", "HPC")
    assert profile.credible_adjacent == ("Cloud architecture",)
    assert profile.learning_or_gap == ("Rust",)
    assert profile.avoid == ("Commission-only sales",)
    page.close()


def test_profile_page_imports_resume_into_private_data(tmp_path: Path) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    resume = tmp_path / "resume.txt"
    resume.write_text("Skills\nPython and Linux", encoding="utf-8")
    page = ProfilePage(database, tmp_path / "data")

    with patch.object(
        QFileDialog, "getOpenFileName", return_value=(str(resume), "")
    ):
        page._choose_resume()
    page.name_input.setText("Candidate")
    page._save()

    profile = get_candidate_profile(database)
    assert profile is not None
    assert profile.resume_source_path is not None
    assert Path(profile.resume_source_path).read_text() == resume.read_text()
    assert profile.resume_normalized_text_path is not None
    assert Path(profile.resume_normalized_text_path).read_text() == resume.read_text()
    page.close()


def test_workbench_opens_as_developer_tool(tmp_path: Path) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    workbench = QMainWindow()
    window = JuniorMainWindow(
        database, tmp_path, workbench_factory=lambda _job: workbench
    )

    window._open_workbench()

    assert workbench.isVisible()
    assert window._workbenches == [workbench]
    workbench.close()
    window.close()


def test_application_editor_round_trips_complete_workflow() -> None:
    _application()
    record = ApplicationRecord(
        "jr-acme-42",
        "Acme",
        "Platform Engineer",
        "https://example/jobs/42",
        "applied",
        "2026-09-08",
        "Phone screen",
        "Follow up Tuesday",
        "2026-09-01",
        "2026-09-02",
    )

    editor = ApplicationEditorDialog(application=record)

    assert editor.application() == record
    editor.close()


def test_company_editor_preserves_source_specific_settings() -> None:
    _application()
    editor = CompanyEditorDialog(
        company={
            "company_key": "hpe",
            "name": "HPE",
            "source_type": "workday",
            "source_url": "https://example/jobs",
            "source_slug": None,
            "source_settings": {
                "source_base_url": "https://example/careers",
                "page_size": 20,
            },
            "enabled": 1,
            "notes": "Test source",
        }
    )

    company = editor.company()

    assert company["source_type"] == "workday"
    assert company["source_settings"] == {
        "page_size": 20,
        "source_base_url": "https://example/careers",
    }
    editor.close()
