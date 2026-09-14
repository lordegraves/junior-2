import json
import os
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication, QFileDialog, QMainWindow

from junior.desktop.main_window import (
    ApplicationEditorDialog,
    CompaniesPage,
    CompanyEditorDialog,
    EmailSettingsPage,
    JuniorMainWindow,
    ProfilePage,
    ReportsPage,
    ScanPage,
)
from junior.domain.lifecycle import ApplicationRecord, CandidateProfile
from junior.infrastructure.application_database import (
    get_candidate_profile,
    initialize_database,
    save_candidate_profile,
)


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_default_window_is_application_shell_not_workbench(tmp_path: Path) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")

    window = JuniorMainWindow(database, tmp_path)

    assert window.windowTitle() == "Junior 2.0"
    assert [window.navigation.item(row).text() for row in range(10)] == [
        "Home",
        "Profile",
        "Companies",
        "Scans",
        "Review Jobs",
        "Applications",
        "History",
        "Reports",
        "Help",
        "Settings",
    ]
    window.close()


def test_home_cards_navigate_to_their_native_filtered_workflows(
    tmp_path: Path,
) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    window = JuniorMainWindow(database, tmp_path)

    window.home_page.card_widgets[1][0].clicked.emit()

    assert window.navigation.currentRow() == 5
    assert window.applications_page._quick_filter is not None

    window.navigation.setCurrentRow(0)
    window.home_page.latest_cards[0][0].clicked.emit()

    assert window.navigation.currentRow() == 4
    assert window.data_pages[2]._quick_filter is not None
    window.close()


def test_empty_installation_guides_user_to_first_incomplete_setup_step(
    tmp_path: Path,
) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    window = JuniorMainWindow(database, tmp_path)

    assert window.home_page.setup_group.isVisibleTo(window)
    assert window.home_page.setup_steps.item(0).text().startswith("○")

    window.home_page._continue_setup()

    assert window.navigation.currentRow() == 1
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
    page.target_roles_input.setPlainText("Platform Engineer\nHPC Engineer")
    page.locations_input.setPlainText("Fort Collins, Colorado")
    page.location_radius_input.setCurrentIndex(
        page.location_radius_input.findData(50)
    )
    page.levels_input.item(2).setSelected(True)
    page.employment_input.item(0).setSelected(True)
    page.workplace_input.item(0).setSelected(True)
    page.schedule_input.setCurrentText("Day shift")
    page.on_call_input.setCurrentText("Willing to participate")
    page.clearance_input.setCurrentText(
        "Exclude jobs requiring an existing active clearance"
    )
    page.travel_input.setValue(20)
    page.outliers_input.setChecked(True)

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
    assert profile.target_roles == ("Platform Engineer", "HPC Engineer")
    assert profile.seniority_levels == ("Senior",)
    assert profile.preferred_locations == ("Fort Collins, Colorado",)
    assert profile.location_radius_miles == 50
    assert profile.work_arrangements == ("Remote",)
    assert profile.employment_types == ("Full-time",)
    assert profile.schedule_preference == "Day shift"
    assert profile.travel_tolerance == 20
    assert profile.include_strong_location_outliers
    page.close()


def test_job_fit_board_adds_moves_removes_and_persists_signal_cards(
    tmp_path: Path,
) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    page = ProfilePage(database, tmp_path)
    page.name_input.setText("Candidate")
    page.fit_board.term_input.setText("Kubernetes")
    page.fit_board.explanation_input.setText("Operated production clusters")
    page.fit_board._add()
    page.fit_board.term_input.setText("Commission-only sales")
    page.fit_board.category_input.setCurrentIndex(
        page.fit_board.category_input.findData("avoid")
    )
    page.fit_board._add()
    page.fit_board.lists["strong"].setCurrentRow(0)
    page.fit_board.category_input.setCurrentIndex(
        page.fit_board.category_input.findData("review")
    )
    page.fit_board._move()
    page._save()

    profile = get_candidate_profile(database)

    assert profile is not None
    assert profile.core_strengths == ()
    assert profile.credible_adjacent == ("Kubernetes",)
    assert profile.avoid == ("Commission-only sales",)
    assert profile.fit_signals == (
        ("Kubernetes", "review", "Operated production clusters"),
        ("Commission-only sales", "avoid", ""),
    )
    page.close()


def test_job_fit_board_remove_selected_signal() -> None:
    _application()
    from junior.desktop.main_window import FitSignalBoard

    board = FitSignalBoard()
    board.set_signals((("Rust", "ignored", "Not used for matching"),))
    board.lists["ignored"].setCurrentRow(0)

    board._remove()

    assert board.signals() == ()
    assert board.touched
    board.close()


def test_profile_configuration_report_is_privacy_safe_and_structured(
    tmp_path: Path,
) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    private_resume = tmp_path / "private-resume.txt"
    private_resume.write_text("Linux Python", encoding="utf-8")
    save_candidate_profile(
        database,
        CandidateProfile(
            "private",
            "Candidate",
            resume_source_path=str(private_resume),
            resume_normalized_text_path=str(private_resume),
            core_strengths=("Linux", "Python"),
            target_roles=("Platform Engineer",),
        ),
    )
    page = ProfilePage(database, tmp_path)

    report = page._configuration_values(get_candidate_profile(database))

    serialized = json.dumps(report)
    assert str(private_resume) not in serialized
    assert "Linux Python" not in serialized
    assert report["Target work"] == ("Platform Engineer",)
    assert page.report_fit_card[1].text() == "2"
    assert page.configuration_table.rowCount() == len(report)
    page.close()


def test_profile_page_imports_resume_into_private_data(tmp_path: Path) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    resume = tmp_path / "resume.txt"
    resume.write_text("Skills\nPython and Linux", encoding="utf-8")
    page = ProfilePage(database, tmp_path / "data")

    with patch.object(QFileDialog, "getOpenFileName", return_value=(str(resume), "")):
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


def test_settings_page_persists_delivery_credentials_and_schedule(
    tmp_path: Path,
) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    settings = QSettings(str(tmp_path / "junior.ini"), QSettings.Format.IniFormat)
    page = EmailSettingsPage(settings, database, tmp_path)
    page.sender.setText("junior@example.com")
    page.usajobs_email.setText("candidate@example.com")
    page.usajobs_key_env.setText("JUNIOR_USAJOBS_KEY")
    page.schedule_enabled.setChecked(True)
    page.schedule_frequency.setCurrentText("Weekdays")
    page.schedule_time.setText("07:30")
    page.retention_days.setValue(20)

    page._save()

    assert settings.value("email/sender") == "junior@example.com"
    assert settings.value("usajobs/email") == "candidate@example.com"
    assert settings.value("usajobs/api_key_env") == "JUNIOR_USAJOBS_KEY"
    assert settings.value("schedule/enabled", type=bool)
    assert settings.value("schedule/frequency") == "Weekdays"
    assert settings.value("schedule/local_time") == "07:30"
    assert settings.value("retention/report_count", type=int) == 20
    page.close()


def test_settings_page_installs_validated_native_schedule(tmp_path: Path) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    settings = QSettings(str(tmp_path / "junior.ini"), QSettings.Format.IniFormat)
    page = EmailSettingsPage(settings, database, tmp_path)
    page.schedule_enabled.setChecked(True)
    page.schedule_frequency.setCurrentText("Weekdays")
    page.schedule_time.setText("06:45")

    with patch.object(
        page._scheduler, "install", return_value="Schedule ready"
    ) as install:
        page._install_schedule()

    spec = install.call_args.args[0]
    assert spec.weekdays == ("Mon", "Tue", "Wed", "Thu", "Fri")
    assert spec.local_time == "06:45"
    assert page.schedule_status.text() == "Schedule ready"
    page.close()


def test_settings_page_tests_every_enabled_company_source(tmp_path: Path) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    from junior.infrastructure.application_database import save_company

    save_company(
        database,
        company_key="enabled",
        name="Enabled",
        source_type="greenhouse",
        enabled=True,
    )
    save_company(
        database,
        company_key="disabled",
        name="Disabled",
        source_type="lever",
        enabled=False,
    )
    calls = []
    page = EmailSettingsPage(None, database, tmp_path, calls.append)

    page._test_enabled_sources()

    assert calls == [("enabled",)]
    page.close()


def test_settings_administration_requires_explicit_unlock(tmp_path: Path) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    page = EmailSettingsPage(None, database, tmp_path)

    assert not page.admin_backup_button.isEnabled()
    page.admin_confirmation.setText("ADMIN")
    page._unlock_administration()

    assert page.admin_backup_button.isEnabled()
    assert page.admin_diagnostics_button.isEnabled()
    assert page.admin_collectors_button.isEnabled()
    page.close()


def test_usajobs_test_maps_named_secret_without_persisting_it(
    tmp_path: Path,
) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")
    from junior.infrastructure.application_database import save_company

    save_company(
        database,
        company_key="federal",
        name="USAJobs",
        source_type="usajobs",
        enabled=True,
    )
    calls = []
    page = EmailSettingsPage(None, database, tmp_path, calls.append)
    page.usajobs_email.setText("candidate@example.com")
    page.usajobs_key_env.setText("JUNIOR_TEST_USAJOBS_KEY")

    with patch.dict(os.environ, {"JUNIOR_TEST_USAJOBS_KEY": "secret"}, clear=False):
        page._test_usajobs_connection()
        assert os.environ["USAJOBS_USER_AGENT"] == "candidate@example.com"
        assert os.environ["USAJOBS_AUTHORIZATION_KEY"] == "secret"

    assert calls == [("federal",)]
    page.close()


def test_native_workspaces_expose_rc6_sections(tmp_path: Path) -> None:
    _application()
    database = initialize_database(tmp_path / "junior.sqlite3")

    def no_row(_row=None):
        return None

    companies = CompaniesPage(
        database, no_row, no_row, no_row, lambda: None, lambda _keys: None
    )
    scan = ScanPage(database, lambda: None, lambda _keys: None)
    reports = ReportsPage(database, no_row, no_row, no_row)
    settings = EmailSettingsPage(None, database, tmp_path)

    assert [
        companies.tabs.tabText(index) for index in range(companies.tabs.count())
    ] == [
        "Companies",
        "Source health",
        "Import / export",
    ]
    assert [scan.tabs.tabText(index) for index in range(scan.tabs.count())] == [
        "Full scan",
        "Selected companies",
        "History",
    ]
    assert [reports.tabs.tabText(index) for index in range(reports.tabs.count())] == [
        "Current scan",
        "Retained report history",
    ]
    assert settings.tabs.count() == 8
    for page in (companies, scan, reports, settings):
        page.close()
