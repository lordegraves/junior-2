"""Junior's native application shell and first production profile workflow."""

import json
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, QThreadPool, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QPushButton,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from junior.application.scan_service import ScanService, ScanSummary
from junior.application.tracker_workflow import apply_quick_action
from junior.collectors.activate import ActivateCollector
from junior.collectors.ashby_workday import AshbyCollector, WorkdayCollector
from junior.collectors.embedded_page import PhenomCollector, RipplingCollector
from junior.collectors.enterprise_api import JobSynCollector, OracleHCMCollector
from junior.collectors.html_pages import HTMLCollector, WekaCollector
from junior.collectors.icims import ICIMSCollector
from junior.collectors.jibe import JibeCollector
from junior.collectors.json_ats import PublicJsonCollector
from junior.collectors.public_api import SmartRecruitersCollector, USAJobsCollector
from junior.collectors.registry import CollectorRegistry
from junior.collectors.schoolspring import SchoolSpringCollector
from junior.collectors.selectminds import SelectMindsCollector
from junior.collectors.session_api import ADPCollector, DayforceCollector
from junior.domain.lifecycle import ApplicationRecord, CandidateProfile
from junior.infrastructure.application_database import (
    LegacyDatabaseError,
    application_workflow_counts,
    delete_application,
    delete_history_record,
    get_candidate_profile,
    get_company,
    get_history_record,
    get_job,
    import_legacy_database,
    lifecycle_counts,
    list_application_views,
    list_applications,
    list_companies,
    list_job_evaluations,
    list_job_history,
    list_jobs,
    list_report_exports,
    list_scan_runs,
    restore_history_to_tracker,
    save_application,
    save_candidate_profile,
    save_company,
    set_company_enabled,
    set_history_included,
    set_job_status,
    track_job,
    update_history_record,
)
from junior.infrastructure.company_config_import import import_company_config
from junior.infrastructure.diagnostics import run_diagnostics
from junior.infrastructure.history_import import import_history_workbook
from junior.infrastructure.profile_files import import_managed_resume
from junior.reporting.email_sender import send_email_report
from junior.reporting.scan_report import (
    render_html_report,
    render_markdown_report,
    save_report,
)


class EmailSettingsPage(QWidget):
    saved = Signal(str)

    def __init__(
        self, settings: QSettings | None, database_path: Path, data_directory: Path
    ) -> None:
        super().__init__()
        self._settings = settings
        self._database_path = database_path
        self._data_directory = data_directory
        layout = QVBoxLayout(self)
        heading = QLabel("Settings & diagnostics")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        layout.addWidget(QLabel(f"Database: {database_path}"))
        layout.addWidget(QLabel("Local model: managed automatically by Junior"))
        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        self.enabled = QCheckBox("Enable explicit report delivery")
        self.sender = QLineEdit()
        self.sender_name = QLineEdit()
        self.recipients = QLineEdit()
        self.host = QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.username = QLineEdit()
        self.password_env = QLineEdit()
        self.tls = QComboBox()
        self.tls.addItems(("starttls", "ssl", "none"))
        form.addRow("Email", self.enabled)
        form.addRow("Sender", self.sender)
        form.addRow("Sender name", self.sender_name)
        form.addRow("Recipients", self.recipients)
        form.addRow("SMTP host", self.host)
        form.addRow("SMTP port", self.port)
        form.addRow("SMTP username", self.username)
        form.addRow("Password environment variable", self.password_env)
        form.addRow("TLS mode", self.tls)
        layout.addWidget(card)
        save = QPushButton("Save settings")
        save.clicked.connect(self._save)
        layout.addWidget(save)
        diagnostics = QPushButton("Run diagnostics")
        diagnostics.clicked.connect(self._run_diagnostics)
        layout.addWidget(diagnostics)
        self.diagnostics_output = QTextEdit()
        self.diagnostics_output.setReadOnly(True)
        self.diagnostics_output.setFixedHeight(120)
        layout.addWidget(self.diagnostics_output)
        layout.addStretch(1)
        self._load()

    def _load(self) -> None:
        if self._settings is None:
            self.port.setValue(587)
            return
        self.enabled.setChecked(self._settings.value("email/enabled", False, bool))
        self.sender.setText(self._settings.value("email/sender", "", str))
        self.sender_name.setText(
            self._settings.value("email/sender_name", "Junior", str)
        )
        self.recipients.setText(self._settings.value("email/recipients", "", str))
        self.host.setText(self._settings.value("email/smtp_host", "", str))
        self.port.setValue(self._settings.value("email/smtp_port", 587, int))
        self.username.setText(self._settings.value("email/smtp_username", "", str))
        self.password_env.setText(
            self._settings.value("email/smtp_password_env", "JUNIOR_SMTP_PASSWORD", str)
        )
        self.tls.setCurrentText(
            self._settings.value("email/smtp_tls_mode", "starttls", str)
        )

    def _save(self) -> None:
        if self._settings is None:
            self.saved.emit("Settings are unavailable in this session.")
            return
        values = self.values()
        for key, value in values.items():
            stored = ", ".join(value) if key == "recipients" else value
            self._settings.setValue(f"email/{key}", stored)
        self._settings.sync()
        self.saved.emit("Email settings saved. Passwords remain outside Junior.")

    def values(self) -> dict[str, object]:
        return {
            "enabled": self.enabled.isChecked(),
            "sender": self.sender.text().strip(),
            "sender_name": self.sender_name.text().strip(),
            "recipients": [
                item.strip()
                for item in self.recipients.text().split(",")
                if item.strip()
            ],
            "smtp_host": self.host.text().strip(),
            "smtp_port": self.port.value(),
            "smtp_username": self.username.text().strip(),
            "smtp_password_env": self.password_env.text().strip(),
            "smtp_tls_mode": self.tls.currentText(),
        }

    def _run_diagnostics(self) -> None:
        results = run_diagnostics(self._database_path, self._data_directory)
        self.diagnostics_output.setPlainText(
            "\n".join(
                f"{'PASS' if item.passed else 'FAIL'} — {item.name}: {item.detail}"
                for item in results
            )
        )
        passed = sum(item.passed for item in results)
        self.saved.emit(f"Diagnostics complete: {passed}/{len(results)} passed.")


class ProfilePage(QWidget):
    saved = Signal(str)

    def __init__(self, database_path: Path, data_directory: Path) -> None:
        super().__init__()
        self._database_path = database_path
        self._data_directory = data_directory
        self._resume_source_path: str | None = None
        self._resume_normalized_path: str | None = None
        layout = QVBoxLayout(self)
        heading = QLabel("Profile")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        intro = QLabel(
            "Junior uses this profile for deterministic job evaluation. "
            "Your résumé remains on this computer."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        self.name_input = QLineEdit()
        self.name_input.setAccessibleName("Candidate name")
        self.floor_input = _money_input()
        self.preferred_input = _money_input()
        self.resume_label = QLabel("No résumé selected")
        self.resume_label.setWordWrap(True)
        resume_button = QPushButton("Choose résumé…")
        resume_button.clicked.connect(self._choose_resume)
        form.addRow("Name", self.name_input)
        form.addRow("Minimum compensation", self.floor_input)
        form.addRow("Preferred base", self.preferred_input)
        form.addRow("Résumé", self.resume_label)
        form.addRow("", resume_button)
        self.core_strengths_input = _list_input("One demonstrated strength per line")
        self.adjacent_input = _list_input("One credible adjacent skill per line")
        self.gaps_input = _list_input("One learning area or known gap per line")
        self.avoid_input = _list_input(
            "One role, duty, industry, or condition to avoid per line"
        )
        form.addRow("Core strengths", self.core_strengths_input)
        form.addRow("Credible adjacent", self.adjacent_input)
        form.addRow("Learning or gaps", self.gaps_input)
        form.addRow("Avoid", self.avoid_input)
        layout.addWidget(card)

        controls = QHBoxLayout()
        controls.addStretch(1)
        save_button = QPushButton("Save profile")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save)
        controls.addWidget(save_button)
        layout.addLayout(controls)
        layout.addStretch(1)
        self._load()

    def _load(self) -> None:
        profile = get_candidate_profile(self._database_path)
        if profile is None:
            return
        self.name_input.setText(profile.name)
        self.floor_input.setValue(profile.compensation_floor_usd or 0)
        self.preferred_input.setValue(profile.preferred_base_usd or 0)
        self._resume_source_path = profile.resume_source_path
        self._resume_normalized_path = profile.resume_normalized_text_path
        self.core_strengths_input.setPlainText("\n".join(profile.core_strengths))
        self.adjacent_input.setPlainText("\n".join(profile.credible_adjacent))
        self.gaps_input.setPlainText("\n".join(profile.learning_or_gap))
        self.avoid_input.setPlainText("\n".join(profile.avoid))
        if profile.resume_source_path:
            self.resume_label.setText(Path(profile.resume_source_path).name)

    def _choose_resume(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Choose résumé",
            "",
            "Résumé files (*.pdf *.docx *.txt)",
        )
        if not selected:
            return
        try:
            managed = import_managed_resume(selected, self._data_directory)
        except ValueError as error:
            self.saved.emit(str(error))
            return
        self._resume_source_path = managed.source_path
        self._resume_normalized_path = managed.normalized_text_path
        self.resume_label.setText(
            f"{Path(managed.source_path).name} · {managed.character_count:,} characters"
        )
        self.saved.emit("Résumé imported locally. Save the profile to keep it active.")

    def _save(self) -> None:
        try:
            save_candidate_profile(
                self._database_path,
                CandidateProfile(
                    profile_id="default",
                    name=self.name_input.text(),
                    compensation_floor_usd=self.floor_input.value() or None,
                    preferred_base_usd=self.preferred_input.value() or None,
                    resume_source_path=self._resume_source_path,
                    resume_normalized_text_path=self._resume_normalized_path,
                    core_strengths=_lines(self.core_strengths_input),
                    credible_adjacent=_lines(self.adjacent_input),
                    learning_or_gap=_lines(self.gaps_input),
                    avoid=_lines(self.avoid_input),
                ),
            )
        except ValueError as error:
            self.saved.emit(str(error))
            return
        self.saved.emit("Profile saved.")


class ApplicationEditorDialog(QDialog):
    _STATUSES = (
        "review_needed",
        "saved",
        "applied",
        "interviewing",
        "offer",
        "withdrawn",
        "rejected",
    )

    def __init__(
        self,
        parent: QWidget | None = None,
        application: ApplicationRecord | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Application details")
        self.setMinimumWidth(560)
        form = QFormLayout(self)
        self.id_input = QLineEdit(application.job_radar_id if application else "")
        self.company_input = QLineEdit(application.company_name if application else "")
        self.role_input = QLineEdit(application.role_title if application else "")
        self.url_input = QLineEdit(application.source_url or "" if application else "")
        self.status_input = QComboBox()
        self.status_input.addItems(self._STATUSES)
        if application and application.status in self._STATUSES:
            self.status_input.setCurrentText(application.status)
        self.follow_up_input = QLineEdit(
            application.follow_up_on or "" if application else ""
        )
        self.outcome_input = QLineEdit(application.outcome or "" if application else "")
        self.applied_input = QLineEdit(
            application.applied_on or "" if application else ""
        )
        self.activity_input = QLineEdit(
            application.last_activity_on or "" if application else ""
        )
        self.notes_input = QTextEdit(application.notes or "" if application else "")
        self.notes_input.setAcceptRichText(False)
        self.notes_input.setFixedHeight(110)
        form.addRow("Application ID", self.id_input)
        form.addRow("Company", self.company_input)
        form.addRow("Role", self.role_input)
        form.addRow("Posting URL", self.url_input)
        form.addRow("Status", self.status_input)
        form.addRow("Follow-up date (YYYY-MM-DD)", self.follow_up_input)
        form.addRow("Outcome", self.outcome_input)
        form.addRow("Applied date (YYYY-MM-DD)", self.applied_input)
        form.addRow("Last activity (YYYY-MM-DD)", self.activity_input)
        form.addRow("Notes", self.notes_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def application(self) -> ApplicationRecord:
        return ApplicationRecord(
            job_radar_id=self.id_input.text(),
            company_name=self.company_input.text(),
            role_title=self.role_input.text(),
            source_url=_optional_text(self.url_input.text()),
            status=self.status_input.currentText(),
            follow_up_on=_optional_text(self.follow_up_input.text()),
            outcome=_optional_text(self.outcome_input.text()),
            notes=_optional_text(self.notes_input.toPlainText()),
            applied_on=_optional_text(self.applied_input.text()),
            last_activity_on=_optional_text(self.activity_input.text()),
        )


class CompanyEditorDialog(QDialog):
    def __init__(
        self,
        parent: QWidget | None = None,
        company: dict[str, object] | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Company source")
        self.setMinimumWidth(620)
        form = QFormLayout(self)

        def value(key: str) -> str:
            return str(company.get(key) or "") if company else ""

        self.key_input = QLineEdit(value("company_key"))
        self.name_input = QLineEdit(str(company.get("name") or "") if company else "")
        self.type_input = QLineEdit(value("source_type"))
        self.slug_input = QLineEdit(value("source_slug"))
        self.url_input = QLineEdit(value("source_url"))
        self.enabled_input = QCheckBox("Include this company in scans")
        enabled = bool(company.get("enabled", 1)) if company else True
        self.enabled_input.setChecked(enabled)
        settings = company.get("source_settings", {}) if company else {}
        self.settings_input = QTextEdit(json.dumps(settings, indent=2, sort_keys=True))
        self.settings_input.setAcceptRichText(False)
        self.settings_input.setFixedHeight(170)
        self.notes_input = QTextEdit(str(company.get("notes") or "") if company else "")
        self.notes_input.setAcceptRichText(False)
        self.notes_input.setFixedHeight(80)
        form.addRow("Company key", self.key_input)
        form.addRow("Company name", self.name_input)
        form.addRow("Source type", self.type_input)
        form.addRow("Board/account slug", self.slug_input)
        form.addRow("Source URL", self.url_input)
        form.addRow("Additional source settings (JSON)", self.settings_input)
        form.addRow("Notes", self.notes_input)
        form.addRow("", self.enabled_input)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def company(self) -> dict[str, object]:
        try:
            settings = json.loads(self.settings_input.toPlainText() or "{}")
        except json.JSONDecodeError as error:
            message = "Additional source settings must be valid JSON."
            raise ValueError(message) from error
        if not isinstance(settings, dict):
            raise ValueError("Additional source settings must be a JSON object.")
        return {
            "company_key": self.key_input.text(),
            "name": self.name_input.text(),
            "source_type": self.type_input.text(),
            "source_slug": _optional_text(self.slug_input.text()),
            "source_url": _optional_text(self.url_input.text()),
            "source_settings": settings,
            "notes": _optional_text(self.notes_input.toPlainText()),
            "enabled": self.enabled_input.isChecked(),
        }


class HistoryEditorDialog(QDialog):
    def __init__(self, parent: QWidget, record: dict[str, object]) -> None:
        super().__init__(parent)
        self.setWindowTitle("Edit history record")
        self._import_key = str(record["import_key"])
        layout = QFormLayout(self)
        self.company = QLineEdit(str(record.get("company") or ""))
        self.role = QLineEdit(str(record.get("role") or ""))
        self.status = QLineEdit(str(record.get("status") or ""))
        self.outcome = QLineEdit(str(record.get("outcome_category") or ""))
        self.technical = QLineEdit(str(record.get("technical_match") or ""))
        self.primary = QLineEdit(str(record.get("primary_blocker") or ""))
        self.secondary = QLineEdit(str(record.get("secondary_blocker") or ""))
        self.revisit = QLineEdit(str(record.get("revisit") or ""))
        self.notes = QTextEdit(str(record.get("notes") or ""))
        for label, control in (
            ("Company", self.company),
            ("Role", self.role),
            ("Status", self.status),
            ("Outcome", self.outcome),
            ("Technical match", self.technical),
            ("Primary blocker", self.primary),
            ("Secondary blocker", self.secondary),
            ("Revisit", self.revisit),
            ("Notes", self.notes),
        ):
            layout.addRow(label, control)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save
            | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addRow(buttons)

    def values(self) -> dict[str, object]:
        return {
            "import_key": self._import_key,
            "company": self.company.text(),
            "role": self.role.text(),
            "status": _optional_text(self.status.text()),
            "outcome_category": _optional_text(self.outcome.text()),
            "technical_match": _optional_text(self.technical.text()),
            "primary_blocker": _optional_text(self.primary.text()),
            "secondary_blocker": _optional_text(self.secondary.text()),
            "revisit": _optional_text(self.revisit.text()),
            "notes": _optional_text(self.notes.toPlainText()),
        }


class ReportsPage(QWidget):
    def __init__(
        self,
        database_path: Path,
        export_report: Callable[[dict[str, object] | None], None],
        save_preview: Callable[[dict[str, object] | None], None],
        send_email: Callable[[dict[str, object] | None], None],
    ) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        self.evaluations = DataTablePage(
            "Current evaluations",
            (
                "ID",
                "Company",
                "Title",
                "Score",
                "Policy score",
                "Location",
                "Recommendation",
                "Action",
                "Hiring probability",
                "Compensation",
                "Résumé match",
                "Reasons",
                "Created",
            ),
            lambda: list_job_evaluations(database_path),
            actions=(
                ("Export report…", export_report),
                ("Save email preview…", save_preview),
                ("Send email", send_email),
            ),
        )
        self.saved = DataTablePage(
            "Saved reports",
            ("ID", "Path", "Format", "Created"),
            lambda: list_report_exports(database_path),
            actions=(("View report", self._view_report),),
        )
        layout.addWidget(self.evaluations, 2)
        layout.addWidget(self.saved, 1)

    def refresh(self) -> None:
        self.evaluations.refresh()
        self.saved.refresh()

    def _view_report(self, row: dict[str, object] | None) -> None:
        if row is None:
            return
        path = Path(str(row["path"]))
        viewer = QDialog(self)
        viewer.setWindowTitle(path.name)
        viewer.resize(1000, 720)
        layout = QVBoxLayout(viewer)
        content = QTextEdit()
        content.setReadOnly(True)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as error:
            text = f"Could not open the saved report:\n{error}"
        content.setHtml(text) if path.suffix.casefold() in {
            ".html",
            ".htm",
        } else content.setPlainText(text)
        layout.addWidget(content)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.rejected.connect(viewer.reject)
        layout.addWidget(close)
        viewer.exec()


class HomePage(QWidget):
    def __init__(self, database_path: Path) -> None:
        super().__init__()
        self._database_path = database_path
        layout = QVBoxLayout(self)
        heading = QLabel("Junior")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        layout.addWidget(QLabel("Local-first job discovery and application management"))
        self.summary = QLabel()
        self.summary.setObjectName("summary")
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        refresh = QPushButton("Refresh dashboard")
        refresh.clicked.connect(self.refresh)
        layout.addWidget(refresh)
        layout.addStretch(1)
        self.refresh()

    def refresh(self) -> None:
        counts = lifecycle_counts(self._database_path)
        workflow = application_workflow_counts(self._database_path)
        attention = sum(
            workflow.get(key, 0)
            for key in ("follow_up_due", "needs_date_review", "stale", "dormant")
        )
        self.summary.setText(
            f"{counts['job_postings']:,} saved jobs  ·  "
            f"{counts['scan_runs']:,} scans  ·  "
            f"{counts['application_tracker']:,} tracked applications\n\n"
            f"{attention:,} need attention  ·  "
            f"{workflow.get('follow_up_due', 0):,} follow-ups due  ·  "
            f"{workflow.get('active_pipeline', 0):,} active interviews/offers  ·  "
            f"{workflow.get('closed', 0):,} closed"
        )


class JuniorMainWindow(QMainWindow):
    def __init__(
        self,
        database_path: str | Path,
        data_directory: str | Path,
        settings: QSettings | None = None,
        workbench_factory: Callable[[dict[str, object] | None], QMainWindow]
        | None = None,
        qualification_runner: Callable[..., object] | None = None,
        resume_runner: Callable[..., object] | None = None,
    ) -> None:
        super().__init__()
        self._database_path = Path(database_path)
        self._data_directory = Path(data_directory)
        self._settings = settings
        self._workbench_factory = workbench_factory
        self._qualification_runner = qualification_runner
        self._resume_runner = resume_runner
        self._workbenches: list[QMainWindow] = []
        self.setWindowTitle("Junior 2.0")
        self.resize(1280, 820)
        self.setMinimumSize(960, 640)

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        self.navigation = QListWidget()
        self.navigation.setObjectName("navigation")
        self.navigation.setFixedWidth(210)
        for label in (
            "Home",
            "Profile",
            "Companies",
            "Scans",
            "Jobs",
            "Applications",
            "History",
            "Reports",
            "Settings",
        ):
            self.navigation.addItem(label)
        self.pages = QStackedWidget()
        self.home_page = HomePage(self._database_path)
        self.pages.addWidget(self.home_page)
        profile = ProfilePage(self._database_path, Path(data_directory))
        profile.saved.connect(self.statusBar().showMessage)
        self.pages.addWidget(profile)
        self.scan_page = DataTablePage(
            "Scans",
            (
                "Run",
                "Generated",
                "Status",
                "Companies",
                "Jobs",
                "New",
                "Changed",
                "Errors",
                "Review",
            ),
            lambda: list_scan_runs(self._database_path),
            actions=(("Run scan", lambda _row: self._run_scan()),),
        )
        self.data_pages = (
            DataTablePage(
                "Companies",
                ("Key", "Company", "Source", "URL", "Enabled", "Updated"),
                lambda: list_companies(self._database_path),
                actions=(
                    ("Add company…", self._add_company),
                    ("Edit…", self._edit_company),
                    ("Enable / disable", self._toggle_company),
                ),
            ),
            self.scan_page,
            DataTablePage(
                "Jobs",
                ("ID", "Company", "Title", "Location", "Remote", "Status", "Seen"),
                lambda: list_jobs(self._database_path),
                actions=(
                    ("Evaluate", self._evaluate_job),
                    ("Track application", self._track_job),
                    ("Set status…", self._set_job_status),
                ),
            ),
            DataTablePage(
                "Applications",
                (
                    "Job ID",
                    "Company",
                    "Role",
                    "URL",
                    "Status",
                    "Follow up",
                    "Outcome",
                    "Notes",
                    "Applied",
                    "Activity",
                    "Workflow",
                ),
                lambda: list_application_views(self._database_path),
                actions=(
                    ("Add application…", self._add_application),
                    ("Edit…", self._update_application),
                    ("Quick action…", self._quick_application_action),
                    ("Remove", self._delete_application),
                ),
            ),
            DataTablePage(
                "History",
                (
                    "Import key",
                    "Type",
                    "Company",
                    "Role",
                    "Status",
                    "Outcome",
                    "Date",
                    "Primary blocker",
                    "Revisit",
                    "Included",
                ),
                lambda: list_job_history(self._database_path),
                actions=(
                    ("Edit…", self._edit_history),
                    ("Include / exclude", self._toggle_history),
                    ("Restore to applications", self._restore_history),
                    ("Delete", self._delete_history),
                ),
            ),
            ReportsPage(
                self._database_path,
                self._export_report,
                self._save_email_preview,
                self._send_email,
            ),
        )
        for page in self.data_pages:
            self.pages.addWidget(page)
        self.settings_page = EmailSettingsPage(
            self._settings, self._database_path, self._data_directory
        )
        self.settings_page.saved.connect(self.statusBar().showMessage)
        self.pages.addWidget(self.settings_page)
        self.navigation.currentRowChanged.connect(self.pages.setCurrentIndex)
        self.navigation.setCurrentRow(0)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self._build_menu()
        self.setStyleSheet(_STYLE)

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("&File")
        import_action = file_menu.addAction("Import Junior 1.x data…")
        import_action.triggered.connect(self._import_legacy_data)
        import_companies = file_menu.addAction("Import Junior 1.x companies…")
        import_companies.triggered.connect(self._import_company_config)
        import_history = file_menu.addAction("Import job history workbook…")
        import_history.triggered.connect(self._import_history)
        tools = self.menuBar().addMenu("&Tools")
        workbench = tools.addAction("Qualification Workbench…")
        workbench.setEnabled(self._workbench_factory is not None)
        workbench.triggered.connect(self._open_workbench)

    def _import_legacy_data(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Import Junior 1.x data",
            "",
            "SQLite databases (*.sqlite *.sqlite3 *.db);;All files (*)",
        )
        if not selected:
            return
        try:
            summary = import_legacy_database(selected, self._database_path)
        except LegacyDatabaseError as error:
            self.statusBar().showMessage(str(error))
            return
        if not summary.imported:
            self.statusBar().showMessage(
                "That unchanged database was already imported."
            )
            return
        for page in self.data_pages:
            page.refresh()
        count = sum(value for _, value in summary.table_counts)
        self.statusBar().showMessage(f"Imported {count:,} Junior 1.x records.")

    def _import_company_config(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Import Junior 1.x companies",
            "",
            "YAML files (*.yaml *.yml);;All files (*)",
        )
        if not selected:
            return
        try:
            count = import_company_config(selected, self._database_path)
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            return
        self.data_pages[0].refresh()
        self.statusBar().showMessage(f"Imported {count:,} company configurations.")

    def _import_history(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self,
            "Import job history",
            "",
            "Excel workbooks (*.xlsx);;All files (*)",
        )
        if not selected:
            return
        try:
            summary = import_history_workbook(self._database_path, selected)
        except (OSError, ValueError) as error:
            self.statusBar().showMessage(str(error))
            return
        self.data_pages[3].refresh()
        self.data_pages[4].refresh()
        self.statusBar().showMessage(
            f"Imported {summary.rows_imported:,} history rows; "
            f"skipped {summary.rows_skipped:,}."
        )

    def _open_workbench(self) -> None:
        if self._workbench_factory is None:
            return
        window = self._workbench_factory(None)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.destroyed.connect(lambda: self._forget_workbench(window))
        self._workbenches.append(window)
        window.show()

    def _evaluate_job(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select a job first.")
            return
        if self._workbench_factory is None:
            self.statusBar().showMessage("The evaluation workbench is unavailable.")
            return
        job = get_job(self._database_path, int(row["id"]))
        if job is None:
            self.statusBar().showMessage("The selected job no longer exists.")
            return
        window = self._workbench_factory(job)
        window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        window.destroyed.connect(lambda: self._forget_workbench(window))
        self._workbenches.append(window)
        window.show()

    def _add_company(self, _row: dict[str, object] | None) -> None:
        editor = CompanyEditorDialog(self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        self._save_company_editor(editor)

    def _edit_company(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select a company first.")
            return
        company = get_company(self._database_path, str(row["company_key"]))
        if company is None:
            self.statusBar().showMessage("The selected company no longer exists.")
            return
        editor = CompanyEditorDialog(self, company)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        self._save_company_editor(editor)

    def _save_company_editor(self, editor: CompanyEditorDialog) -> None:
        try:
            company = editor.company()
            save_company(self._database_path, **company)
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            return
        self.data_pages[0].refresh()
        self.statusBar().showMessage(f"Saved {company['name']}.")

    def _run_scan(self) -> None:
        registry = CollectorRegistry(
            {
                "greenhouse": PublicJsonCollector("greenhouse"),
                "lever": PublicJsonCollector("lever"),
                "ashby": AshbyCollector(),
                "workday": WorkdayCollector(),
                "smartrecruiters": SmartRecruitersCollector(),
                "usajobs": USAJobsCollector(),
                "rippling": RipplingCollector(),
                "phenom": PhenomCollector(),
                "oracle_hcm": OracleHCMCollector(),
                "jobsyn": JobSynCollector(),
                "adp": ADPCollector(),
                "dayforce": DayforceCollector(),
                "jibe": JibeCollector(),
                "html": HTMLCollector(),
                "weka": WekaCollector(),
                "selectminds": SelectMindsCollector(),
                "activate": ActivateCollector(),
                "icims": ICIMSCollector(),
                "schoolspring": SchoolSpringCollector(),
            }
        )
        self.statusBar().showMessage("Scanning enabled companies…")
        self._scan_task = ScanTask(
            ScanService(
                self._database_path,
                registry,
                qualification_runner=self._qualification_runner,
                resume_runner=self._resume_runner,
            )
        )
        self._scan_task.signals.finished.connect(self._scan_finished)
        self._scan_task.signals.failed.connect(self._scan_failed)
        QThreadPool.globalInstance().start(self._scan_task)

    def _scan_finished(self, summary: ScanSummary) -> None:
        self.scan_page.refresh()
        self.data_pages[2].refresh()
        self.statusBar().showMessage(
            f"Scan {summary.run_id} complete: {summary.jobs_collected} jobs, "
            f"{summary.jobs_new} new, {summary.errors} errors."
        )

    def _scan_failed(self, message: str) -> None:
        self.scan_page.refresh()
        self.statusBar().showMessage(f"Scan failed: {message}")

    def _toggle_company(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select a company first.")
            return
        enabled = not bool(row["enabled"])
        set_company_enabled(self._database_path, str(row["company_key"]), enabled)
        self.data_pages[0].refresh()
        state = "enabled" if enabled else "disabled"
        self.statusBar().showMessage(f"{row['name']} {state}.")

    def _track_job(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select a job first.")
            return
        job_radar_id = track_job(self._database_path, int(row["id"]))
        self.data_pages[3].refresh()
        self.statusBar().showMessage(f"Tracking {job_radar_id}.")

    def _set_job_status(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select a job first.")
            return
        options = ("new", "reviewing", "saved", "passed", "archived")
        status, accepted = QInputDialog.getItem(
            self, "Job status", "Status", options, editable=False
        )
        if not accepted:
            return
        set_job_status(self._database_path, int(row["id"]), status)
        self.data_pages[2].refresh()
        self.statusBar().showMessage(f"Job marked {status}.")

    def _update_application(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select an application first.")
            return
        application = ApplicationRecord(
            job_radar_id=str(row["job_radar_id"]),
            company_name=str(row["company_name"]),
            role_title=str(row["role_title"]),
            source_url=_optional_text(row["source_url"]),
            status=str(row["status"]),
            follow_up_on=_optional_text(row["follow_up_on"]),
            outcome=_optional_text(row["outcome"]),
            notes=_optional_text(row["notes"]),
            applied_on=_optional_text(row["applied_on"]),
            last_activity_on=_optional_text(row["last_activity_on"]),
        )
        editor = ApplicationEditorDialog(self, application)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            save_application(self._database_path, editor.application())
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            return
        self.data_pages[3].refresh()
        self.home_page.refresh()
        self.statusBar().showMessage("Application updated.")

    def _add_application(self, _row: dict[str, object] | None) -> None:
        editor = ApplicationEditorDialog(self)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            save_application(self._database_path, editor.application())
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            return
        self.data_pages[3].refresh()
        self.home_page.refresh()
        self.statusBar().showMessage("Application added.")

    def _quick_application_action(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select an application first.")
            return
        options = {
            "Refresh activity today": "refresh_activity_today",
            "Schedule follow-up next week": "follow_up_next_week",
            "Mark follow-up due": "follow_up_due",
            "Mark dormant": "dormant",
            "Mark interview scheduled": "interview_scheduled",
            "Mark waiting for feedback": "waiting_for_feedback",
        }
        label, accepted = QInputDialog.getItem(
            self, "Application quick action", "Action", tuple(options), editable=False
        )
        if not accepted:
            return
        application = next(
            (
                item
                for item in list_applications(self._database_path)
                if item.job_radar_id == str(row["job_radar_id"])
            ),
            None,
        )
        if application is None:
            self.statusBar().showMessage("The selected application no longer exists.")
            return
        save_application(
            self._database_path, apply_quick_action(application, options[label])
        )
        self.data_pages[3].refresh()
        self.home_page.refresh()
        self.statusBar().showMessage(f"Applied: {label}.")

    def _delete_application(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select an application first.")
            return
        delete_application(self._database_path, str(row["job_radar_id"]))
        self.data_pages[3].refresh()
        self.home_page.refresh()
        self.statusBar().showMessage("Application removed from tracking.")

    def _toggle_history(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select a history record first.")
            return
        included = not bool(row["include_in_job_radar"])
        set_history_included(self._database_path, str(row["import_key"]), included)
        self.data_pages[4].refresh()
        state = "included" if included else "excluded"
        self.statusBar().showMessage(f"History record {state} in scan matching.")

    def _edit_history(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select a history record first.")
            return
        record = get_history_record(self._database_path, str(row["import_key"]))
        if record is None:
            self.statusBar().showMessage("The history record no longer exists.")
            return
        editor = HistoryEditorDialog(self, record)
        if editor.exec() != QDialog.DialogCode.Accepted:
            return
        values = editor.values()
        import_key = str(values.pop("import_key"))
        try:
            update_history_record(self._database_path, import_key, **values)
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            return
        self.data_pages[4].refresh()
        self.statusBar().showMessage("History record updated.")

    def _delete_history(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select a history record first.")
            return
        delete_history_record(self._database_path, str(row["import_key"]))
        self.data_pages[4].refresh()
        self.statusBar().showMessage("History record deleted.")

    def _restore_history(self, row: dict[str, object] | None) -> None:
        if row is None:
            self.statusBar().showMessage("Select a history record first.")
            return
        try:
            application_id = restore_history_to_tracker(
                self._database_path, str(row["import_key"])
            )
        except ValueError as error:
            self.statusBar().showMessage(str(error))
            return
        self.data_pages[3].refresh()
        self.home_page.refresh()
        self.statusBar().showMessage(f"Restored {application_id} to applications.")

    def _export_report(self, _row: dict[str, object] | None) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export scan report",
            "junior-scan-report.html",
            "HTML report (*.html);;Markdown report (*.md)",
        )
        if not destination:
            return
        try:
            saved = save_report(self._database_path, destination)
        except OSError as error:
            self.statusBar().showMessage(f"Could not save report: {error}")
            return
        self.statusBar().showMessage(f"Report saved to {saved}.")
        self.data_pages[5].refresh()

    def _save_email_preview(self, _row: dict[str, object] | None) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Save email preview",
            "junior-email-preview.txt",
            "Text preview (*.txt)",
        )
        if not destination:
            return
        try:
            Path(destination).write_text(
                render_markdown_report(self._database_path), encoding="utf-8"
            )
        except OSError as error:
            self.statusBar().showMessage(f"Could not save preview: {error}")
            return
        self.statusBar().showMessage(f"Email preview saved to {destination}.")

    def _send_email(self, _row: dict[str, object] | None) -> None:
        result = send_email_report(
            self.settings_page.values(),
            "Junior 2.0 scan report",
            render_markdown_report(self._database_path),
            render_html_report(self._database_path),
        )
        self.statusBar().showMessage(result.message)

    def _forget_workbench(self, window: QMainWindow) -> None:
        if window in self._workbenches:
            self._workbenches.remove(window)


def _money_input() -> QSpinBox:
    control = QSpinBox()
    control.setRange(0, 2_000_000)
    control.setSingleStep(5_000)
    control.setPrefix("$")
    control.setSpecialValueText("Not set")
    return control


def _list_input(placeholder: str) -> QTextEdit:
    control = QTextEdit()
    control.setPlaceholderText(placeholder)
    control.setAcceptRichText(False)
    control.setFixedHeight(82)
    return control


def _lines(control: QTextEdit) -> tuple[str, ...]:
    return tuple(
        line.strip() for line in control.toPlainText().splitlines() if line.strip()
    )


def _coming_page(name: str) -> QWidget:
    page = QWidget()
    layout = QVBoxLayout(page)
    heading = QLabel(name)
    heading.setObjectName("pageHeading")
    layout.addWidget(heading)
    message = QLabel(f"The native {name.lower()} workflow is the next migration slice.")
    message.setWordWrap(True)
    layout.addWidget(message)
    layout.addStretch(1)
    return page


class DataTablePage(QWidget):
    def __init__(
        self,
        name: str,
        headers: tuple[str, ...],
        loader: Callable[[], tuple[dict[str, object], ...]],
        actions: tuple[
            tuple[str, Callable[[dict[str, object] | None], None]], ...
        ] = (),
    ) -> None:
        super().__init__()
        self._loader = loader
        self._all_rows: tuple[dict[str, object], ...] = ()
        self._rows: tuple[dict[str, object], ...] = ()
        layout = QVBoxLayout(self)
        heading_row = QHBoxLayout()
        heading = QLabel(name)
        heading.setObjectName("pageHeading")
        refresh = QPushButton("Refresh")
        refresh.clicked.connect(self.refresh)
        heading_row.addWidget(heading)
        heading_row.addStretch(1)
        for label, callback in actions:
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, handler=callback: handler(self.selected_row())
            )
            heading_row.addWidget(button)
        heading_row.addWidget(refresh)
        layout.addLayout(heading_row)
        self.search = QLineEdit()
        self.search.setPlaceholderText(f"Search {name.casefold()}…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        layout.addWidget(self.search)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSortingEnabled(True)
        layout.addWidget(self.table, 1)
        self.refresh()

    def refresh(self) -> None:
        self._all_rows = self._loader()
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self.search.text().strip().casefold()
        rows = tuple(
            row
            for row in self._all_rows
            if not needle
            or needle in " ".join(str(value or "") for value in row.values()).casefold()
        )
        self._rows = rows
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row.values()):
                display = (
                    "Yes" if value == 1 else "No" if value == 0 else str(value or "")
                )
                item = QTableWidgetItem(display)
                item.setData(Qt.ItemDataRole.UserRole, row_index)
                self.table.setItem(row_index, column_index, item)
        self.table.resizeColumnsToContents()
        self.table.setSortingEnabled(True)

    def selected_row(self) -> dict[str, object] | None:
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        source_row = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if source_row is None or not 0 <= int(source_row) < len(self._rows):
            return None
        return self._rows[int(source_row)]


class ScanSignals(QObject):
    finished = Signal(object)
    failed = Signal(str)


class ScanTask(QRunnable):
    def __init__(self, service: ScanService) -> None:
        super().__init__()
        self._service = service
        self.signals = ScanSignals()

    def run(self) -> None:
        try:
            summary = self._service.run()
        except Exception as error:
            self.signals.failed.emit(str(error))
            return
        self.signals.finished.emit(summary)


def _slug(value: str) -> str:
    return "-".join(value.lower().split())


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


_STYLE = """
QMainWindow, QWidget { background: #12161c; color: #eef3f8; font-size: 14px; }
#navigation { background: #18202a; border: 0; padding: 18px 8px; }
#navigation::item { padding: 13px 14px; border-radius: 6px; }
#navigation::item:selected { background: #175f89; }
#pageHeading { font-size: 28px; font-weight: 700; margin: 20px 8px 8px 8px; }
#summary, #card { background: #1c242e; border: 1px solid #344250;
  border-radius: 8px; padding: 18px; }
QLineEdit, QSpinBox, QTextEdit { background: #202832; border: 1px solid #465463;
  border-radius: 4px; padding: 7px; }
QPushButton { padding: 8px 14px; }
#primaryButton { background: #1878ac; border-radius: 5px; }
QStatusBar { background: #18202a; }
"""
