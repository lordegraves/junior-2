"""Junior's native application shell and first production profile workflow."""

import json
import os
import platform
import shutil
from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QObject, QRunnable, QSettings, Qt, QThreadPool, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from junior import __version__
from junior.application.role_discovery import (
    list_role_suggestions,
    record_role_feedback,
    refresh_role_suggestions,
)
from junior.application.scan_service import ScanService, ScanSummary
from junior.application.tracker_workflow import apply_quick_action
from junior.collectors.activate import ActivateCollector
from junior.collectors.ashby_workday import AshbyCollector, WorkdayCollector
from junior.collectors.contracts import CollectorSource
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
    create_candidate_profile,
    delete_application,
    delete_candidate_profile,
    delete_history_record,
    export_candidate_profile,
    get_candidate_profile,
    get_company,
    get_history_record,
    get_job,
    import_candidate_profile,
    import_legacy_database,
    lifecycle_counts,
    list_application_views,
    list_applications,
    list_candidate_profiles,
    list_companies,
    list_company_source_health,
    list_job_evaluations,
    list_job_history,
    list_jobs,
    list_report_exports,
    list_review_jobs,
    list_scan_errors,
    list_scan_runs,
    restore_history_to_tracker,
    save_application,
    save_candidate_profile,
    save_company,
    save_company_source_health,
    set_active_candidate_profile,
    set_company_enabled,
    set_history_included,
    set_job_status,
    track_job,
    update_history_record,
)
from junior.infrastructure.company_config_import import import_company_config
from junior.infrastructure.diagnostics import create_support_bundle, run_diagnostics
from junior.infrastructure.history_import import import_history_workbook
from junior.infrastructure.profile_files import import_managed_resume
from junior.infrastructure.reference_catalog import (
    suggest_locations,
    suggest_occupations,
)
from junior.infrastructure.retention import apply_retention
from junior.infrastructure.scheduler import (
    SchedulerError,
    SchedulerIntegration,
    ScheduleSpec,
)
from junior.reporting.email_sender import send_email_report, test_email_connection
from junior.reporting.scan_report import (
    render_html_report,
    render_markdown_report,
    save_report,
)


class EmailSettingsPage(QWidget):
    saved = Signal(str)

    def __init__(
        self,
        settings: QSettings | None,
        database_path: Path,
        data_directory: Path,
        source_test_callback: Callable[[tuple[str, ...]], None] | None = None,
    ) -> None:
        super().__init__()
        self._settings = settings
        self._database_path = database_path
        self._data_directory = data_directory
        self._source_test_callback = source_test_callback
        self._scheduler = SchedulerIntegration(data_directory)
        layout = QVBoxLayout(self)
        heading = QLabel("Settings & diagnostics")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        layout.addWidget(QLabel(f"Database: {database_path}"))
        layout.addWidget(QLabel("Local model: managed automatically by Junior"))
        tabs = self.tabs = QTabWidget()
        delivery_page = QWidget()
        delivery_layout = QVBoxLayout(delivery_page)
        card = QFrame()
        card.setObjectName("card")
        form = QFormLayout(card)
        self.enabled = QCheckBox("Enable explicit report delivery")
        self.provider = QComboBox()
        self.provider.addItems(("Gmail", "Outlook / Microsoft 365", "Custom SMTP"))
        self.provider.currentTextChanged.connect(self._apply_provider_defaults)
        self.sender = QLineEdit()
        self.sender_name = QLineEdit()
        self.recipients = QLineEdit()
        self.host = QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.username = QLineEdit()
        self.password_env = QLineEdit()
        self.password_env.setEchoMode(QLineEdit.EchoMode.Password)
        self.tls = QComboBox()
        self.tls.addItems(("starttls", "ssl", "none"))
        form.addRow("Email", self.enabled)
        form.addRow("Provider", self.provider)
        form.addRow("Sender", self.sender)
        form.addRow("Sender name", self.sender_name)
        form.addRow("Recipients", self.recipients)
        form.addRow("SMTP host", self.host)
        form.addRow("SMTP port", self.port)
        form.addRow("SMTP username", self.username)
        form.addRow("Password environment variable", self.password_env)
        form.addRow("TLS mode", self.tls)
        test_email = QPushButton("Test connection")
        test_email.clicked.connect(self._test_email_settings)
        form.addRow("", test_email)
        delivery_layout.addWidget(card)
        save = QPushButton("Save settings")
        save.clicked.connect(self._save)
        delivery_layout.addWidget(save)
        delivery_layout.addStretch(1)
        tabs.addTab(delivery_page, "Email delivery")

        credentials_page = QWidget()
        credentials = QFormLayout(credentials_page)
        self.usajobs_email = QLineEdit()
        self.usajobs_key_env = QLineEdit()
        self.usajobs_key_env.setPlaceholderText("USAJOBS_API_KEY")
        credentials.addRow("USAJobs account email", self.usajobs_email)
        credentials.addRow("USAJobs API-key environment variable", self.usajobs_key_env)
        self.test_usajobs_button = QPushButton("Test USAJobs connection")
        self.test_usajobs_button.clicked.connect(self._test_usajobs_connection)
        credentials.addRow("", self.test_usajobs_button)
        tabs.addTab(credentials_page, "Source credentials")

        automation_page = QWidget()
        automation = QFormLayout(automation_page)
        self.schedule_enabled = QCheckBox("Run scans automatically")
        self.schedule_frequency = QComboBox()
        self.schedule_frequency.addItems(("Daily", "Weekdays", "Weekly"))
        self.schedule_time = QLineEdit()
        self.schedule_time.setPlaceholderText("08:00")
        self.schedule_email = QCheckBox("Email the completed scheduled-scan report")
        self.weekday_checks = tuple(
            QCheckBox(day) for day in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
        )
        weekday_row = QHBoxLayout()
        for check in self.weekday_checks:
            weekday_row.addWidget(check)
        automation.addRow("Scheduled scans", self.schedule_enabled)
        automation.addRow("Frequency", self.schedule_frequency)
        automation.addRow("Local start time", self.schedule_time)
        automation.addRow("Run on", weekday_row)
        automation.addRow("Delivery", self.schedule_email)
        schedule_actions = QHBoxLayout()
        self.install_schedule_button = QPushButton("Install / update schedule")
        self.install_schedule_button.clicked.connect(self._install_schedule)
        self.remove_schedule_button = QPushButton("Remove schedule")
        self.remove_schedule_button.clicked.connect(self._remove_schedule)
        schedule_actions.addWidget(self.install_schedule_button)
        schedule_actions.addWidget(self.remove_schedule_button)
        automation.addRow("Operating system", schedule_actions)
        self.schedule_status = QLabel("Not installed in this session")
        self.schedule_status.setWordWrap(True)
        automation.addRow("Status", self.schedule_status)
        tabs.addTab(automation_page, "Scan schedule")

        retention_page = QWidget()
        retention = QFormLayout(retention_page)
        self.report_retention_policy = QComboBox()
        self.report_retention_policy.addItems(("Keep latest runs", "Keep all"))
        self.report_retention_count = QSpinBox()
        self.report_retention_count.setRange(1, 50)
        self.log_retention_policy = QComboBox()
        self.log_retention_policy.addItems(("Keep latest logs", "Keep all"))
        self.log_retention_count = QSpinBox()
        self.log_retention_count.setRange(1, 50)
        self.retention_days = self.report_retention_count
        retention.addRow("Report history", self.report_retention_policy)
        retention.addRow("Number of report runs", self.report_retention_count)
        retention.addRow("Dated log history", self.log_retention_policy)
        retention.addRow("Number of dated logs", self.log_retention_count)
        apply_retention_button = QPushButton("Save and apply retention")
        apply_retention_button.clicked.connect(self._apply_retention)
        retention.addRow("", apply_retention_button)
        tabs.addTab(retention_page, "Retention")

        diagnostics_page = QWidget()
        diagnostics_layout = QVBoxLayout(diagnostics_page)
        diagnostics = QPushButton("Run diagnostics")
        diagnostics.clicked.connect(self._run_diagnostics)
        diagnostics_layout.addWidget(diagnostics)
        self.test_sources_button = QPushButton("Test enabled company sources")
        self.test_sources_button.clicked.connect(self._test_enabled_sources)
        diagnostics_layout.addWidget(self.test_sources_button)
        support_bundle = QPushButton("Export troubleshooting bundle…")
        support_bundle.clicked.connect(self._export_support_bundle)
        diagnostics_layout.addWidget(support_bundle)
        self.diagnostics_output = QTextEdit()
        self.diagnostics_output.setReadOnly(True)
        diagnostics_layout.addWidget(self.diagnostics_output, 1)
        tabs.addTab(diagnostics_page, "Diagnostics && source health")

        platforms_page = QWidget()
        platforms_layout = QVBoxLayout(platforms_page)
        platforms_layout.addWidget(
            QLabel("Collector catalog and installed source adapters")
        )
        platform_list = QListWidget()
        platform_list.addItems(_collector_names())
        platforms_layout.addWidget(platform_list, 1)
        tabs.addTab(platforms_page, "Job platforms")

        administration_page = QWidget()
        administration = QFormLayout(administration_page)
        self.admin_confirmation = QLineEdit()
        self.admin_confirmation.setPlaceholderText("Type ADMIN to unlock controls")
        administration.addRow(
            "Administration confirmation", self.admin_confirmation
        )
        self.admin_unlock_button = QPushButton("Unlock administration")
        self.admin_unlock_button.clicked.connect(self._unlock_administration)
        administration.addRow("", self.admin_unlock_button)
        self.admin_backup_button = QPushButton("Create database backup…")
        self.admin_backup_button.setEnabled(False)
        self.admin_backup_button.clicked.connect(self._backup_database)
        administration.addRow("Recovery", self.admin_backup_button)
        self.admin_diagnostics_button = QPushButton("Open diagnostics")
        self.admin_diagnostics_button.setEnabled(False)
        self.admin_diagnostics_button.clicked.connect(lambda: tabs.setCurrentIndex(4))
        administration.addRow("Health", self.admin_diagnostics_button)
        self.admin_collectors_button = QPushButton("Open collector catalog")
        self.admin_collectors_button.setEnabled(False)
        self.admin_collectors_button.clicked.connect(lambda: tabs.setCurrentIndex(5))
        administration.addRow("Collectors", self.admin_collectors_button)
        tabs.addTab(administration_page, "Administration")

        ai_page = QWidget()
        ai_layout = QVBoxLayout(ai_page)
        ai_layout.addWidget(QLabel("AI résumé tailoring — under development"))
        ai_layout.addStretch(1)
        tabs.addTab(ai_page, "AI résumé tailoring")
        layout.addWidget(tabs, 1)
        self._load()

    def _load(self) -> None:
        if self._settings is None:
            self.port.setValue(587)
            return
        self.enabled.setChecked(self._settings.value("email/enabled", False, bool))
        self.provider.setCurrentText(
            self._settings.value("email/provider", "Custom SMTP", str)
        )
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
        self.usajobs_email.setText(self._settings.value("usajobs/email", "", str))
        self.usajobs_key_env.setText(
            self._settings.value("usajobs/api_key_env", "USAJOBS_API_KEY", str)
        )
        self.schedule_enabled.setChecked(
            self._settings.value("schedule/enabled", False, bool)
        )
        self.schedule_frequency.setCurrentText(
            self._settings.value("schedule/frequency", "Daily", str)
        )
        self.schedule_time.setText(
            self._settings.value("schedule/local_time", "08:00", str)
        )
        selected_days = set(
            self._settings.value(
                "schedule/weekdays", ("Mon", "Tue", "Wed", "Thu", "Fri"), list
            )
        )
        for check in self.weekday_checks:
            check.setChecked(check.text() in selected_days)
        self.schedule_email.setChecked(
            self._settings.value("schedule/email_delivery", False, bool)
        )
        self.report_retention_policy.setCurrentText(
            self._settings.value("retention/report_policy", "Keep latest runs", str)
        )
        self.report_retention_count.setValue(
            self._settings.value("retention/report_count", 10, int)
        )
        self.log_retention_policy.setCurrentText(
            self._settings.value("retention/log_policy", "Keep latest logs", str)
        )
        self.log_retention_count.setValue(
            self._settings.value("retention/log_count", 10, int)
        )

    def _save(self) -> None:
        if self._settings is None:
            self.saved.emit("Settings are unavailable in this session.")
            return
        values = self.values()
        for key, value in values.items():
            stored = ", ".join(value) if key == "recipients" else value
            self._settings.setValue(f"email/{key}", stored)
        self._settings.setValue("usajobs/email", self.usajobs_email.text().strip())
        self._settings.setValue(
            "usajobs/api_key_env", self.usajobs_key_env.text().strip()
        )
        self._settings.setValue("schedule/enabled", self.schedule_enabled.isChecked())
        self._settings.setValue(
            "schedule/frequency", self.schedule_frequency.currentText()
        )
        self._settings.setValue(
            "schedule/local_time", self.schedule_time.text().strip()
        )
        self._settings.setValue(
            "schedule/weekdays",
            [check.text() for check in self.weekday_checks if check.isChecked()],
        )
        self._settings.setValue(
            "schedule/email_delivery", self.schedule_email.isChecked()
        )
        self._settings.setValue(
            "retention/report_policy", self.report_retention_policy.currentText()
        )
        self._settings.setValue(
            "retention/report_count", self.report_retention_count.value()
        )
        self._settings.setValue(
            "retention/log_policy", self.log_retention_policy.currentText()
        )
        self._settings.setValue("retention/log_count", self.log_retention_count.value())
        self._settings.sync()
        self._apply_usajobs_environment()
        self.saved.emit("Email settings saved. Passwords remain outside Junior.")

    def values(self) -> dict[str, object]:
        return {
            "enabled": self.enabled.isChecked(),
            "provider": self.provider.currentText(),
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

    def _apply_retention(self) -> None:
        self._save()
        result = apply_retention(
            self._database_path,
            self._data_directory,
            report_count=(
                self.report_retention_count.value()
                if self.report_retention_policy.currentText() == "Keep latest runs"
                else None
            ),
            log_count=(
                self.log_retention_count.value()
                if self.log_retention_policy.currentText() == "Keep latest logs"
                else None
            ),
        )
        self.saved.emit(
            "Retention applied: "
            f"{result.report_records_removed} report records and "
            f"{result.log_files_removed} logs removed."
        )

    def _export_support_bundle(self) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export troubleshooting bundle",
            "junior-2-support.zip",
            "ZIP archives (*.zip)",
        )
        if not destination:
            return
        try:
            output = create_support_bundle(
                destination, self._database_path, self._data_directory
            )
        except (OSError, ValueError) as error:
            self.saved.emit(f"Could not export troubleshooting bundle: {error}")
            return
        self.saved.emit(f"Troubleshooting bundle exported to {output}.")

    def _test_enabled_sources(self) -> None:
        if self._source_test_callback is None:
            self.saved.emit("Source testing is unavailable in this session.")
            return
        keys = tuple(
            str(company["company_key"])
            for company in list_companies(self._database_path)
            if company.get("enabled")
        )
        if not keys:
            self.saved.emit("No enabled company sources are available to test.")
            return
        self._source_test_callback(keys)

    def _test_usajobs_connection(self) -> None:
        if not self.usajobs_email.text().strip():
            self.saved.emit("Enter the USAJobs account email first.")
            return
        if not self.usajobs_key_env.text().strip():
            self.saved.emit("Enter the environment variable holding the API key.")
            return
        rows = tuple(
            company
            for company in list_companies(self._database_path)
            if company.get("enabled") and company.get("source_type") == "usajobs"
        )
        if not rows:
            self.saved.emit(
                "Add and enable a USAJobs company source before testing credentials."
            )
            return
        if self._source_test_callback is None:
            self.saved.emit("USAJobs source testing is unavailable in this session.")
            return
        if not self._apply_usajobs_environment():
            return
        self._source_test_callback(
            tuple(str(company["company_key"]) for company in rows)
        )

    def _apply_usajobs_environment(self) -> bool:
        email = self.usajobs_email.text().strip()
        key_variable = self.usajobs_key_env.text().strip()
        authorization_key = os.environ.get(key_variable) if key_variable else None
        if email:
            os.environ["USAJOBS_USER_AGENT"] = email
        if authorization_key:
            os.environ["USAJOBS_AUTHORIZATION_KEY"] = authorization_key
        elif key_variable:
            self.saved.emit(
                f"The USAJobs API-key environment variable is not set: {key_variable}"
            )
        return bool(email and authorization_key)

    def _test_email_settings(self) -> None:
        values = self.values()
        missing = [
            label
            for label, key in (
                ("SMTP host", "smtp_host"),
                ("SMTP username", "smtp_username"),
                ("password environment variable", "smtp_password_env"),
            )
            if not values.get(key)
        ]
        if missing:
            self.saved.emit("Email connection is incomplete: " + ", ".join(missing))
            return
        result = test_email_connection(values)
        self.saved.emit(result.message)

    def _apply_provider_defaults(self, provider: str) -> None:
        defaults = {
            "Gmail": ("smtp.gmail.com", 587, "starttls"),
            "Outlook / Microsoft 365": ("smtp.office365.com", 587, "starttls"),
        }
        if provider not in defaults:
            return
        host, port, tls = defaults[provider]
        self.host.setText(host)
        self.port.setValue(port)
        self.tls.setCurrentText(tls)

    def _schedule_spec(self) -> ScheduleSpec:
        frequency = self.schedule_frequency.currentText()
        selected = tuple(
            check.text() for check in self.weekday_checks if check.isChecked()
        )
        if frequency == "Daily":
            selected = tuple(check.text() for check in self.weekday_checks)
        elif frequency == "Weekdays":
            selected = ("Mon", "Tue", "Wed", "Thu", "Fri")
        elif frequency == "Weekly" and len(selected) != 1:
            raise SchedulerError("Select exactly one day for a weekly scan.")
        return ScheduleSpec(
            self.schedule_enabled.isChecked(),
            self.schedule_time.text().strip(),
            selected,
        )

    def _install_schedule(self) -> None:
        try:
            self._save()
            message = self._scheduler.install(self._schedule_spec())
        except (OSError, SchedulerError) as error:
            message = f"Could not install the schedule: {error}"
        self.schedule_status.setText(message)
        self.saved.emit(message)

    def _remove_schedule(self) -> None:
        try:
            message = self._scheduler.remove()
        except (OSError, SchedulerError) as error:
            message = f"Could not remove the schedule: {error}"
        self.schedule_status.setText(message)
        self.saved.emit(message)

    def _unlock_administration(self) -> None:
        unlocked = self.admin_confirmation.text().strip() == "ADMIN"
        for control in (
            self.admin_backup_button,
            self.admin_diagnostics_button,
            self.admin_collectors_button,
        ):
            control.setEnabled(unlocked)
        self.admin_confirmation.clear()
        self.saved.emit(
            "Administration unlocked for this window."
            if unlocked
            else "Type ADMIN exactly to unlock administration."
        )

    def _backup_database(self) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Back up Junior data",
            "junior-2-backup.sqlite3",
            "SQLite database (*.sqlite3)",
        )
        if not destination:
            return
        try:
            shutil.copy2(self._database_path, destination)
        except OSError as error:
            self.saved.emit(f"Could not create backup: {error}")
            return
        self.saved.emit(f"Database backup created at {destination}.")


class FitSignalBoard(QWidget):
    """Native four-category editor for durable job-fit signal cards."""

    CATEGORIES = (
        ("strong", "Strong Match"),
        ("review", "Needs Review"),
        ("avoid", "Avoid"),
        ("ignored", "Ignored"),
    )

    def __init__(self) -> None:
        super().__init__()
        self.touched = False
        self.lists: dict[str, QListWidget] = {}
        layout = QVBoxLayout(self)
        columns = QGridLayout()
        for index, (category, label) in enumerate(self.CATEGORIES):
            group = QGroupBox(label)
            group_layout = QVBoxLayout(group)
            control = QListWidget()
            control.setAccessibleName(f"{label} job-fit signals")
            control.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
            control.itemSelectionChanged.connect(
                lambda selected=category: self._selected(selected)
            )
            group_layout.addWidget(control)
            columns.addWidget(group, 0, index)
            self.lists[category] = control
        layout.addLayout(columns, 1)

        editor = QGroupBox("Add or update a skill or responsibility")
        editor_layout = QGridLayout(editor)
        self.term_input = QLineEdit()
        self.term_input.setPlaceholderText("Example: inventory management")
        self.explanation_input = QLineEdit()
        self.explanation_input.setPlaceholderText(
            "Optional evidence or reason for this classification"
        )
        self.category_input = QComboBox()
        for category, label in self.CATEGORIES:
            self.category_input.addItem(label, category)
        add = QPushButton("Add signal")
        add.clicked.connect(self._add)
        move = QPushButton("Move selected")
        move.clicked.connect(self._move)
        remove = QPushButton("Remove selected")
        remove.clicked.connect(self._remove)
        editor_layout.addWidget(QLabel("Signal"), 0, 0)
        editor_layout.addWidget(self.term_input, 0, 1)
        editor_layout.addWidget(QLabel("Explanation"), 1, 0)
        editor_layout.addWidget(self.explanation_input, 1, 1)
        editor_layout.addWidget(self.category_input, 0, 2)
        editor_layout.addWidget(add, 0, 3)
        editor_layout.addWidget(move, 1, 2)
        editor_layout.addWidget(remove, 1, 3)
        layout.addWidget(editor)

    def set_signals(self, signals: tuple[tuple[str, ...], ...]) -> None:
        for control in self.lists.values():
            control.clear()
        for signal in signals:
            if len(signal) < 2 or signal[1] not in self.lists:
                continue
            explanation = signal[2] if len(signal) > 2 else ""
            self._insert(signal[0], signal[1], explanation)
        self.touched = False

    def signals(self) -> tuple[tuple[str, str, str], ...]:
        values: list[tuple[str, str, str]] = []
        for category, _label in self.CATEGORIES:
            control = self.lists[category]
            for index in range(control.count()):
                item = control.item(index)
                values.append(
                    (
                        item.text(),
                        category,
                        str(item.data(Qt.ItemDataRole.UserRole) or ""),
                    )
                )
        return tuple(values)

    def _insert(self, term: str, category: str, explanation: str) -> None:
        item = QListWidgetItem(term.strip())
        item.setData(Qt.ItemDataRole.UserRole, explanation.strip())
        item.setToolTip(explanation.strip() or "No explanation recorded.")
        self.lists[category].addItem(item)

    def _add(self) -> None:
        term = self.term_input.text().strip()
        if not term:
            return
        existing = {signal[0].casefold() for signal in self.signals()}
        if term.casefold() not in existing:
            self._insert(
                term,
                str(self.category_input.currentData()),
                self.explanation_input.text(),
            )
            self.touched = True
        self.term_input.clear()
        self.explanation_input.clear()

    def _current(self) -> tuple[str, QListWidget, QListWidgetItem] | None:
        for category, control in self.lists.items():
            if (item := control.currentItem()) is not None:
                return category, control, item
        return None

    def _selected(self, category: str) -> None:
        if self.lists[category].currentItem() is None:
            return
        for other, control in self.lists.items():
            if other != category:
                control.clearSelection()

    def _move(self) -> None:
        current = self._current()
        if current is None:
            return
        source_category, source, item = current
        destination = str(self.category_input.currentData())
        if destination == source_category:
            return
        row = source.row(item)
        moved = source.takeItem(row)
        self.lists[destination].addItem(moved)
        self.lists[destination].setCurrentItem(moved)
        self.touched = True

    def _remove(self) -> None:
        current = self._current()
        if current is None:
            return
        _category, source, item = current
        source.takeItem(source.row(item))
        self.touched = True


class ProfilePage(QWidget):
    saved = Signal(str)

    JOB_LEVELS = ("Entry-level", "Mid-level", "Senior", "Executive")
    EMPLOYMENT_TYPES = (
        "Full-time",
        "Part-time",
        "Contract",
        "Temporary",
        "Seasonal",
        "Internship or apprenticeship",
    )
    WORKPLACES = ("Remote", "Hybrid", "On-site", "Flex")
    SCHEDULES = (
        "Any schedule",
        "Day shift",
        "Evening shift",
        "Night shift",
        "Weekdays",
        "Weekends accepted",
        "Flexible schedule",
    )
    ON_CALL = (
        "Willing to participate",
        "Not willing to participate",
        "Review each job",
    )
    CLEARANCE = (
        "I hold an active clearance",
        "Exclude jobs requiring an existing active clearance",
        "Review each job",
    )

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

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs, 1)

        overview = QWidget()
        overview_layout = QVBoxLayout(overview)
        self.cards = QGridLayout()
        self.card_name = _status_card("Active candidate")
        self.card_floor = _status_card("Compensation floor")
        self.card_target = _status_card("Preferred base")
        self.card_resume = _status_card("Active résumé")
        self.card_ready = _status_card("Profile and résumé state")
        for index, card in enumerate(
            (
                self.card_name,
                self.card_floor,
                self.card_target,
                self.card_resume,
                self.card_ready,
            )
        ):
            self.cards.addWidget(card[0], 0, index)
        overview_layout.addLayout(self.cards)

        card = QGroupBox("Search profile")
        form = QFormLayout(card)
        self.name_input = QLineEdit()
        self.name_input.setAccessibleName("Candidate name")
        self.floor_input = _money_input()
        self.preferred_input = _money_input()
        form.addRow("Name", self.name_input)
        form.addRow("Minimum compensation", self.floor_input)
        form.addRow("Preferred base", self.preferred_input)
        self.target_roles_input = _list_input("One occupation or target role per line")
        self.locations_input = _list_input("One preferred location per line")
        self.avoid_input = _list_input(
            "One role, duty, industry, or condition to avoid per line"
        )
        role_picker = QWidget()
        role_picker_layout = QVBoxLayout(role_picker)
        role_picker_layout.setContentsMargins(0, 0, 0, 0)
        self.role_search_input = QLineEdit()
        self.role_search_input.setPlaceholderText(
            "Search O*NET occupations and alternate job titles"
        )
        self.role_search_results = QListWidget()
        self.role_search_results.setFixedHeight(120)
        self.role_search_results.hide()
        self.target_roles_input.setMaximumHeight(90)
        self.role_search_input.textChanged.connect(self._search_roles)
        self.role_search_results.itemDoubleClicked.connect(self._add_role_result)
        role_picker_layout.addWidget(self.role_search_input)
        role_picker_layout.addWidget(self.role_search_results)
        role_picker_layout.addWidget(self.target_roles_input)
        form.addRow("Target work", role_picker)
        self.levels_input = _multi_choice(self.JOB_LEVELS)
        self.employment_input = _multi_choice(self.EMPLOYMENT_TYPES)
        self.workplace_input = _multi_choice(self.WORKPLACES)
        form.addRow("Job levels", self.levels_input)
        form.addRow("Employment types", self.employment_input)
        form.addRow("Workplace arrangements", self.workplace_input)
        location_picker = QWidget()
        location_picker_layout = QVBoxLayout(location_picker)
        location_picker_layout.setContentsMargins(0, 0, 0, 0)
        self.location_search_input = QLineEdit()
        self.location_search_input.setPlaceholderText("Search U.S. city, state, or ZIP")
        self.location_search_results = QListWidget()
        self.location_search_results.setFixedHeight(120)
        self.location_search_results.hide()
        self.locations_input.setMaximumHeight(90)
        self.location_search_input.textChanged.connect(self._search_locations)
        self.location_search_results.itemDoubleClicked.connect(
            self._add_location_result
        )
        location_picker_layout.addWidget(self.location_search_input)
        location_picker_layout.addWidget(self.location_search_results)
        location_picker_layout.addWidget(self.locations_input)
        form.addRow("Preferred locations", location_picker)
        self.location_radius_input = QComboBox()
        for radius in (10, 25, 50, 75, 100):
            self.location_radius_input.addItem(f"Within {radius} miles", radius)
        form.addRow("Commute distance", self.location_radius_input)
        self.schedule_input = QComboBox()
        self.schedule_input.addItems(self.SCHEDULES)
        self.on_call_input = QComboBox()
        self.on_call_input.addItems(self.ON_CALL)
        self.clearance_input = QComboBox()
        self.clearance_input.addItems(self.CLEARANCE)
        self.travel_input = QSpinBox()
        self.travel_input.setRange(0, 100)
        self.travel_input.setSuffix("%")
        self.travel_unrestricted_input = QCheckBox("Accept any travel amount")
        self.travel_unrestricted_input.toggled.connect(
            lambda checked: self.travel_input.setDisabled(checked)
        )
        self.outliers_input = QCheckBox(
            "Show strong matches outside preferred areas in a separate review group"
        )
        form.addRow("Schedule", self.schedule_input)
        form.addRow("On-call", self.on_call_input)
        form.addRow("Security clearance", self.clearance_input)
        form.addRow("Maximum travel", self.travel_input)
        form.addRow("Travel limit", self.travel_unrestricted_input)
        form.addRow("Outside-area matches", self.outliers_input)
        form.addRow("Work you do not want", self.avoid_input)
        overview_layout.addWidget(card)
        self.scan_summary = QLabel()
        self.scan_summary.setWordWrap(True)
        self.scan_summary.setObjectName("card")
        overview_layout.addWidget(self.scan_summary)
        overview_layout.addStretch(1)
        overview_scroll = QScrollArea()
        overview_scroll.setWidgetResizable(True)
        overview_scroll.setFrameShape(QFrame.Shape.NoFrame)
        overview_scroll.setWidget(overview)
        self.tabs.addTab(overview_scroll, "Overview")

        resume_tab = QWidget()
        resume_layout = QVBoxLayout(resume_tab)
        resume_status = QGroupBox("Active résumé")
        resume_form = QFormLayout(resume_status)
        self.resume_label = QLabel("No résumé selected")
        self.resume_label.setWordWrap(True)
        resume_button = QPushButton("Choose or replace résumé…")
        resume_button.clicked.connect(self._choose_resume)
        resume_form.addRow("Current file", self.resume_label)
        resume_form.addRow("", resume_button)
        resume_layout.addWidget(resume_status)
        self.resume_preview = QTextEdit()
        self.resume_preview.setReadOnly(True)
        self.resume_preview.setPlaceholderText("No résumé preview is available.")
        resume_layout.addWidget(self.resume_preview, 1)
        self.tabs.addTab(resume_tab, "Résumé")

        fit_tab = QWidget()
        fit_page_layout = QVBoxLayout(fit_tab)
        fit_cards = QHBoxLayout()
        self.fit_summary_cards = tuple(
            _status_card(caption)
            for caption in (
                "Strong matches",
                "Needs review",
                "Learning / gaps",
                "Avoid signals",
            )
        )
        for card in self.fit_summary_cards:
            fit_cards.addWidget(card[0])
        fit_page_layout.addLayout(fit_cards)
        self.fit_board = FitSignalBoard()
        self.core_strengths_input = _list_input("One demonstrated strength per line")
        self.adjacent_input = _list_input("One credible adjacent skill per line")
        self.gaps_input = _list_input("One learning area or known gap per line")
        self.avoid_fit_input = _list_input("One avoid signal per line")
        for control in (
            self.core_strengths_input,
            self.adjacent_input,
            self.gaps_input,
            self.avoid_fit_input,
        ):
            control.hide()
        fit_page_layout.addWidget(self.fit_board, 1)
        fit_help = QLabel(
            "Select a signal, choose its destination, and use Move selected. "
            "Strong Match and Needs Review contribute positive résumé evidence; "
            "Avoid can block a recommendation, and Ignored is not scored."
        )
        fit_help.setWordWrap(True)
        fit_help.setObjectName("muted")
        fit_page_layout.addWidget(fit_help)
        self.tabs.addTab(fit_tab, "Job fit")

        discovery = QWidget()
        discovery_layout = QVBoxLayout(discovery)
        discovery_layout.addWidget(
            QLabel(
                "Role discovery uses the active résumé and saved fit signals to expose "
                "credible adjacent occupations without changing scan rules "
                "automatically."
            )
        )
        discovery_actions = QHBoxLayout()
        generate = QPushButton("Generate suggestions")
        generate.clicked.connect(self._generate_role_suggestions)
        discovery_actions.addWidget(generate)
        for label, state in (
            ("Relevant", "relevant"),
            ("Not relevant", "not_relevant"),
            ("Different discipline", "different_discipline"),
        ):
            button = QPushButton(label)
            button.clicked.connect(
                lambda _checked=False, value=state: self._record_role_feedback(value)
            )
            discovery_actions.addWidget(button)
        discovery_actions.addStretch(1)
        discovery_layout.addLayout(discovery_actions)
        self.discovery_table = QTableWidget(0, 5)
        self.discovery_table.setHorizontalHeaderLabels(
            ("Suggested role", "Employer", "Evidence", "Decision", "Why")
        )
        self.discovery_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.discovery_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.discovery_table.horizontalHeader().setStretchLastSection(True)
        discovery_layout.addWidget(self.discovery_table, 1)
        self.tabs.addTab(discovery, "Role discovery")

        report = QWidget()
        report_layout = QVBoxLayout(report)
        report_intro = QLabel(
            "Privacy-safe profile configuration. Résumé text, local file paths, "
            "credentials, and secrets are excluded."
        )
        report_intro.setWordWrap(True)
        report_layout.addWidget(report_intro)
        report_cards = QHBoxLayout()
        self.report_profile_card = _status_card("Profile")
        self.report_company_card = _status_card("Companies selected for scanning")
        self.report_fit_card = _status_card("Configured job-fit signals")
        self.report_ready_card = _status_card("Configuration state")
        for card in (
            self.report_profile_card,
            self.report_company_card,
            self.report_fit_card,
            self.report_ready_card,
        ):
            report_cards.addWidget(card[0])
        report_layout.addLayout(report_cards)
        self.configuration_table = QTableWidget(0, 2)
        self.configuration_table.setHorizontalHeaderLabels(("Setting", "Value"))
        self.configuration_table.setEditTriggers(
            QTableWidget.EditTrigger.NoEditTriggers
        )
        self.configuration_table.horizontalHeader().setStretchLastSection(True)
        report_layout.addWidget(self.configuration_table, 1)
        report_actions = QHBoxLayout()
        report_actions.addStretch(1)
        export_configuration = QPushButton("Export configuration report…")
        export_configuration.clicked.connect(self._export_configuration_report)
        report_actions.addWidget(export_configuration)
        report_layout.addLayout(report_actions)
        self.configuration_report = QTextEdit()
        self.configuration_report.setReadOnly(True)
        self.configuration_report.setVisible(False)
        self.tabs.addTab(report, "Configuration report")

        manage = QWidget()
        manage_layout = QVBoxLayout(manage)
        manage_card = QGroupBox("Manage profiles")
        manage_form = QFormLayout(manage_card)
        self.profile_selector = QComboBox()
        self.profile_selector.currentIndexChanged.connect(self._profile_selected)
        manage_form.addRow("Saved profiles", self.profile_selector)
        buttons = QHBoxLayout()
        for label, callback in (
            ("Use this profile", self._activate_profile),
            ("Create profile…", self._create_profile),
            ("Delete profile", self._delete_profile),
            ("Export profile…", self._export_profile),
            ("Import profile…", self._import_profile),
        ):
            button = QPushButton(label)
            button.clicked.connect(callback)
            buttons.addWidget(button)
        manage_form.addRow(buttons)
        manage_layout.addWidget(manage_card)
        manage_layout.addStretch(1)
        self.tabs.addTab(manage, "Manage profiles")

        controls = QHBoxLayout()
        controls.addStretch(1)
        save_button = QPushButton("Save profile")
        save_button.setObjectName("primaryButton")
        save_button.clicked.connect(self._save)
        controls.addWidget(save_button)
        layout.addLayout(controls)
        self._load()

    def _search_roles(self, query: str) -> None:
        self.role_search_results.clear()
        for suggestion in suggest_occupations(query):
            item = QListWidgetItem(suggestion["label"])
            item.setToolTip(suggestion["description"])
            item.setData(Qt.ItemDataRole.UserRole, suggestion["label"])
            self.role_search_results.addItem(item)
        self.role_search_results.setVisible(self.role_search_results.count() > 0)

    def _add_role_result(self, item: QListWidgetItem) -> None:
        _append_unique_line(
            self.target_roles_input,
            str(item.data(Qt.ItemDataRole.UserRole)),
        )
        self.role_search_input.clear()

    def _search_locations(self, query: str) -> None:
        self.location_search_results.clear()
        for suggestion in suggest_locations(query):
            item = QListWidgetItem(str(suggestion["label"]))
            item.setData(Qt.ItemDataRole.UserRole, suggestion["label"])
            self.location_search_results.addItem(item)
        self.location_search_results.setVisible(
            self.location_search_results.count() > 0
        )

    def _add_location_result(self, item: QListWidgetItem) -> None:
        _append_unique_line(
            self.locations_input,
            str(item.data(Qt.ItemDataRole.UserRole)),
        )
        self.location_search_input.clear()

    def _load(self) -> None:
        profile = get_candidate_profile(self._database_path)
        if profile is None:
            self._reload_profiles()
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
        self.avoid_fit_input.setPlainText("\n".join(profile.avoid))
        signals = profile.fit_signals or tuple(
            (term, category, "")
            for category, terms in (
                ("strong", profile.core_strengths),
                ("review", profile.credible_adjacent),
                ("review", profile.learning_or_gap),
                ("avoid", profile.avoid),
            )
            for term in terms
        )
        self.fit_board.set_signals(signals)
        self.target_roles_input.setPlainText("\n".join(profile.target_roles))
        self.locations_input.setPlainText("\n".join(profile.preferred_locations))
        radius_index = self.location_radius_input.findData(
            profile.location_radius_miles
        )
        self.location_radius_input.setCurrentIndex(max(0, radius_index))
        _select_choices(self.levels_input, profile.seniority_levels)
        _select_choices(self.employment_input, profile.employment_types)
        _select_choices(self.workplace_input, profile.work_arrangements)
        self.schedule_input.setCurrentText(profile.schedule_preference)
        self.on_call_input.setCurrentText(profile.on_call_preference)
        self.clearance_input.setCurrentText(profile.clearance_preference)
        self.travel_unrestricted_input.setChecked(profile.travel_tolerance is None)
        self.travel_input.setValue(profile.travel_tolerance or 0)
        self.outliers_input.setChecked(profile.include_strong_location_outliers)
        if profile.resume_source_path:
            self.resume_label.setText(Path(profile.resume_source_path).name)
        self._refresh_profile_views(profile)

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
        active = get_candidate_profile(self._database_path)
        fit_signals = self.fit_board.signals() if self.fit_board.touched else ()
        strengths = (
            tuple(signal[0] for signal in fit_signals if signal[1] == "strong")
            if fit_signals
            else _lines(self.core_strengths_input)
        )
        adjacent = (
            tuple(signal[0] for signal in fit_signals if signal[1] == "review")
            if fit_signals
            else _lines(self.adjacent_input)
        )
        avoid = (
            tuple(signal[0] for signal in fit_signals if signal[1] == "avoid")
            if fit_signals
            else tuple(
                dict.fromkeys(
                    _lines(self.avoid_input) + _lines(self.avoid_fit_input)
                )
            )
        )
        try:
            save_candidate_profile(
                self._database_path,
                CandidateProfile(
                    profile_id=active.profile_id if active else "default",
                    name=self.name_input.text(),
                    compensation_floor_usd=self.floor_input.value() or None,
                    preferred_base_usd=self.preferred_input.value() or None,
                    resume_source_path=self._resume_source_path,
                    resume_normalized_text_path=self._resume_normalized_path,
                    core_strengths=strengths,
                    credible_adjacent=adjacent,
                    learning_or_gap=_lines(self.gaps_input),
                    avoid=avoid,
                    target_roles=_lines(self.target_roles_input),
                    seniority_levels=_selected_choices(self.levels_input),
                    preferred_locations=_lines(self.locations_input),
                    location_radius_miles=int(
                        self.location_radius_input.currentData()
                    ),
                    work_arrangements=_selected_choices(self.workplace_input),
                    employment_types=_selected_choices(self.employment_input),
                    schedule_preference=self.schedule_input.currentText(),
                    on_call_preference=self.on_call_input.currentText(),
                    clearance_preference=self.clearance_input.currentText(),
                    travel_tolerance=(
                        None
                        if self.travel_unrestricted_input.isChecked()
                        else self.travel_input.value()
                    ),
                    include_strong_location_outliers=self.outliers_input.isChecked(),
                    fit_signals=fit_signals or (active.fit_signals if active else ()),
                ),
            )
        except ValueError as error:
            self.saved.emit(str(error))
            return
        self._reload_profiles()
        self._load()
        self.saved.emit("Profile saved.")

    def _refresh_profile_views(self, profile: CandidateProfile) -> None:
        values = (
            (self.card_name, profile.name),
            (self.card_floor, _money(profile.compensation_floor_usd)),
            (self.card_target, _money(profile.preferred_base_usd)),
            (
                self.card_resume,
                Path(profile.resume_source_path).name
                if profile.resume_source_path
                else "No résumé",
            ),
            (
                self.card_ready,
                "Ready" if profile.resume_normalized_text_path else "Needs attention",
            ),
        )
        for card, value in values:
            card[1].setText(value)
        self.scan_summary.setText(
            "What Junior will scan for\n\n"
            f"Target work: {', '.join(profile.target_roles) or 'Any role'}\n"
            f"Job levels: {', '.join(profile.seniority_levels) or 'Any level'}\n"
            f"Employment: {', '.join(profile.employment_types) or 'Any type'}\n"
            f"Workplace: {', '.join(profile.work_arrangements) or 'Any arrangement'}\n"
            f"Locations: {', '.join(profile.preferred_locations) or 'Any location'}\n"
            f"Commute radius: {profile.location_radius_miles} miles\n"
            "Outside-area matches: "
            f"{'Enabled' if profile.include_strong_location_outliers else 'Disabled'}\n"
            f"Schedule: {profile.schedule_preference}\n"
            f"On-call: {profile.on_call_preference}\n"
            f"Security clearance: {profile.clearance_preference}\n"
            "Travel: "
            + (
                "Any amount"
                if profile.travel_tolerance is None
                else f"up to {profile.travel_tolerance}%"
            )
        )
        preview = ""
        if profile.resume_normalized_text_path:
            try:
                preview = Path(profile.resume_normalized_text_path).read_text(
                    encoding="utf-8"
                )
            except OSError:
                pass
        self.resume_preview.setPlainText(preview)
        if profile.fit_signals:
            fit_values = tuple(
                tuple(signal for signal in profile.fit_signals if signal[1] == category)
                for category in ("strong", "review", "ignored", "avoid")
            )
        else:
            fit_values = (
                profile.core_strengths,
                profile.credible_adjacent,
                profile.learning_or_gap,
                profile.avoid,
            )
        for card, terms in zip(self.fit_summary_cards, fit_values, strict=True):
            card[1].setText(str(len(terms)))
        self._refresh_role_suggestions(profile.profile_id)
        report = self._configuration_values(profile)
        self.configuration_report.setPlainText(
            json.dumps(report, indent=2, ensure_ascii=False)
        )
        self.configuration_table.setRowCount(len(report))
        for row, (label, value) in enumerate(report.items()):
            self.configuration_table.setItem(row, 0, QTableWidgetItem(label))
            self.configuration_table.setItem(
                row, 1, QTableWidgetItem(self._configuration_display(value))
            )
        enabled_companies = sum(
            bool(company.get("enabled"))
            for company in list_companies(self._database_path)
        )
        report_cards = (
            (self.report_profile_card, profile.name),
            (self.report_company_card, str(enabled_companies)),
            (self.report_fit_card, str(sum(len(value) for value in fit_values))),
            (
                self.report_ready_card,
                "Ready" if profile.resume_normalized_text_path else "Needs résumé",
            ),
        )
        for card, value in report_cards:
            card[1].setText(value)
        self._reload_profiles()

    def _configuration_values(self, profile: CandidateProfile) -> dict[str, object]:
        values = export_candidate_profile(profile)
        values.pop("schema_version", None)
        return {
            "Profile name": values.pop("name", profile.name),
            "Compensation floor": _money(profile.compensation_floor_usd),
            "Preferred base": _money(profile.preferred_base_usd),
            "Target work": profile.target_roles,
            "Job levels": profile.seniority_levels,
            "Employment types": profile.employment_types,
            "Workplace arrangements": profile.work_arrangements,
            "Preferred locations": profile.preferred_locations,
            "Commute distance": f"Within {profile.location_radius_miles} miles",
            "Schedule": profile.schedule_preference,
            "On-call": profile.on_call_preference,
            "Security clearance": profile.clearance_preference,
            "Maximum travel": (
                "Any amount"
                if profile.travel_tolerance is None
                else f"{profile.travel_tolerance}%"
            ),
            "Outside-area matches": profile.include_strong_location_outliers,
            "Strong-match signals": profile.core_strengths,
            "Needs-review signals": profile.credible_adjacent,
            "Learning or gaps": profile.learning_or_gap,
            "Avoid signals": profile.avoid,
        }

    @staticmethod
    def _configuration_display(value: object) -> str:
        if isinstance(value, (tuple, list)):
            return ", ".join(str(item) for item in value) or "Not configured"
        if isinstance(value, bool):
            return "Enabled" if value else "Disabled"
        return str(value)

    def _export_configuration_report(self) -> None:
        profile = get_candidate_profile(self._database_path)
        if profile is None:
            self.saved.emit("No active profile is available to export.")
            return
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export profile configuration",
            f"{_slug(profile.name)}-configuration.json",
            "JSON files (*.json)",
        )
        if not destination:
            return
        try:
            Path(destination).write_text(
                json.dumps(
                    self._configuration_values(profile),
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except OSError as error:
            self.saved.emit(f"Could not export configuration: {error}")
            return
        self.saved.emit(f"Configuration report exported to {destination}.")

    def _refresh_role_suggestions(self, profile_id: str) -> None:
        suggestions = list_role_suggestions(self._database_path, profile_id)
        self.discovery_table.setRowCount(len(suggestions))
        for row_index, suggestion in enumerate(suggestions):
            values = (
                suggestion.suggested_title,
                suggestion.employer_context or "All employers",
                ", ".join(suggestion.evidence),
                suggestion.feedback_state.replace("_", " ").title(),
                suggestion.explanation,
            )
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, suggestion.suggestion_id)
                self.discovery_table.setItem(row_index, column, item)

    def _generate_role_suggestions(self) -> None:
        profile = get_candidate_profile(self._database_path)
        if profile is None:
            self.saved.emit("Create a profile before generating role suggestions.")
            return
        try:
            suggestions = refresh_role_suggestions(
                self._database_path, profile.profile_id
            )
        except ValueError as error:
            self.saved.emit(str(error))
            return
        self._refresh_role_suggestions(profile.profile_id)
        self.saved.emit(f"Generated {len(suggestions)} evidence-backed suggestions.")

    def _record_role_feedback(self, state: str) -> None:
        profile = get_candidate_profile(self._database_path)
        row = self.discovery_table.currentRow()
        if profile is None or row < 0:
            self.saved.emit("Select a role suggestion first.")
            return
        suggestion_id = self.discovery_table.item(row, 0).data(
            Qt.ItemDataRole.UserRole
        )
        try:
            record_role_feedback(
                self._database_path, profile.profile_id, int(suggestion_id), state
            )
        except ValueError as error:
            self.saved.emit(str(error))
            return
        self._refresh_role_suggestions(profile.profile_id)
        self.saved.emit("Role-discovery feedback saved.")

    def _reload_profiles(self) -> None:
        active = get_candidate_profile(self._database_path)
        self.profile_selector.blockSignals(True)
        self.profile_selector.clear()
        for profile in list_candidate_profiles(self._database_path):
            self.profile_selector.addItem(profile.name, profile.profile_id)
            if active and profile.profile_id == active.profile_id:
                self.profile_selector.setCurrentIndex(self.profile_selector.count() - 1)
        self.profile_selector.blockSignals(False)

    def _profile_selected(self) -> None:
        profile = get_candidate_profile(
            self._database_path, self.profile_selector.currentData()
        )
        if profile:
            self._refresh_profile_views(profile)

    def _activate_profile(self) -> None:
        profile_id = self.profile_selector.currentData()
        if profile_id:
            set_active_candidate_profile(self._database_path, profile_id)
            self._load()
            self.saved.emit("Active profile changed.")

    def _create_profile(self) -> None:
        name, accepted = QInputDialog.getText(self, "Create profile", "Profile name")
        if not accepted:
            return
        try:
            create_candidate_profile(self._database_path, name)
        except ValueError as error:
            self.saved.emit(str(error))
            return
        self._load()
        self.saved.emit("Profile created and selected.")

    def _delete_profile(self) -> None:
        try:
            delete_candidate_profile(
                self._database_path, self.profile_selector.currentData()
            )
        except ValueError as error:
            self.saved.emit(str(error))
            return
        self._load()
        self.saved.emit("Profile deleted.")

    def _export_profile(self) -> None:
        profile = get_candidate_profile(
            self._database_path, self.profile_selector.currentData()
        )
        if profile is None:
            return
        destination, _ = QFileDialog.getSaveFileName(
            self,
            "Export profile",
            f"{_slug(profile.name)}.junior-profile.json",
            "Junior profiles (*.json)",
        )
        if destination:
            Path(destination).write_text(
                json.dumps(export_candidate_profile(profile), indent=2),
                encoding="utf-8",
            )
            self.saved.emit(f"Profile exported to {destination}.")

    def _import_profile(self) -> None:
        selected, _ = QFileDialog.getOpenFileName(
            self, "Import profile", "", "Junior profiles (*.json)"
        )
        if not selected:
            return
        try:
            values = json.loads(Path(selected).read_text(encoding="utf-8"))
            import_candidate_profile(self._database_path, values)
        except (OSError, ValueError, json.JSONDecodeError) as error:
            self.saved.emit(f"Could not import profile: {error}")
            return
        self._load()
        self.saved.emit("Profile imported. Résumé data was not transferred.")


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
        heading = QLabel("Reports & Audit")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        intro = QLabel(
            "View current deterministic results, create portable reports, and "
            "inspect retained report history. Review decisions remain in Review Jobs."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        tabs = self.tabs = QTabWidget()
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
            summary_metrics=(
                ("Evaluated", lambda rows: len(rows)),
                (
                    "Top matches",
                    lambda rows: _count(rows, "recommendation", "top_match"),
                ),
                (
                    "Review needed",
                    lambda rows: _count(rows, "recommendation", "review_needed"),
                ),
                ("Omitted", lambda rows: _count(rows, "recommendation", "omit")),
            ),
            filters=(
                (
                    "Recommendation",
                    "recommendation",
                    ("top_match", "review_needed", "omit"),
                ),
            ),
        )
        self.saved = DataTablePage(
            "Saved reports",
            ("ID", "Path", "Format", "Created"),
            lambda: list_report_exports(database_path),
            actions=(("View report", self._view_report),),
        )
        tabs.addTab(self.evaluations, "Current scan")
        tabs.addTab(self.saved, "Retained report history")
        layout.addWidget(tabs, 1)

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


class ScanPage(QWidget):
    """Native equivalent of RC6's full-scan and selected-company workspace."""

    def __init__(
        self,
        database_path: Path,
        run_all: Callable[[], None],
        run_selected: Callable[[tuple[str, ...]], None],
    ) -> None:
        super().__init__()
        self._database_path = database_path
        self._run_all = run_all
        self._run_selected = run_selected
        layout = QVBoxLayout(self)
        heading = QLabel("Scan")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        tabs = self.tabs = QTabWidget()
        layout.addWidget(tabs, 1)

        run_page = QWidget()
        run_layout = QVBoxLayout(run_page)
        run_card = QGroupBox("Run scan")
        run_card_layout = QVBoxLayout(run_card)
        run_card_layout.addWidget(
            QLabel(
                "Collect and evaluate current jobs from every company enabled for "
                "the active profile. Manual scans do not send email."
            )
        )
        self.run_button = QPushButton("Run scan")
        self.run_button.setObjectName("primaryButton")
        self.run_button.clicked.connect(run_all)
        run_card_layout.addWidget(self.run_button)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.hide()
        run_card_layout.addWidget(self.progress)
        self.stage = QLabel("No scan is currently running.")
        self.stage.setObjectName("muted")
        run_card_layout.addWidget(self.stage)
        run_layout.addWidget(run_card)

        receipt = QGroupBox("Most recent completed full scan")
        receipt_layout = QGridLayout(receipt)
        self.receipt_cards = tuple(
            _status_card(caption)
            for caption in (
                "Company sources",
                "Jobs collected",
                "New jobs",
                "Changed jobs",
                "Need review",
                "Source warnings",
            )
        )
        for index, card in enumerate(self.receipt_cards):
            receipt_layout.addWidget(card[0], index // 3, index % 3)
        run_layout.addWidget(receipt)
        problems = QGroupBox("Company source warnings")
        problems_layout = QVBoxLayout(problems)
        self.problems = QListWidget()
        problems_layout.addWidget(self.problems)
        run_layout.addWidget(problems, 1)
        tabs.addTab(run_page, "Full scan")

        selected_page = QWidget()
        selected_layout = QVBoxLayout(selected_page)
        explanation = QLabel(
            "Scan only the checked companies. Existing save, pass, and apply "
            "decisions remain in effect and stable job identity prevents duplicates."
        )
        explanation.setWordWrap(True)
        selected_layout.addWidget(explanation)
        self.company_choices = QListWidget()
        selected_layout.addWidget(self.company_choices, 1)
        selection_buttons = QHBoxLayout()
        select_all = QPushButton("Select all")
        select_all.clicked.connect(lambda: self._check_all(True))
        clear = QPushButton("Clear")
        clear.clicked.connect(lambda: self._check_all(False))
        run_selected_button = QPushButton("Scan selected companies")
        run_selected_button.setObjectName("primaryButton")
        run_selected_button.clicked.connect(self._start_selected)
        selection_buttons.addWidget(select_all)
        selection_buttons.addWidget(clear)
        selection_buttons.addStretch(1)
        selection_buttons.addWidget(run_selected_button)
        selected_layout.addLayout(selection_buttons)
        tabs.addTab(selected_page, "Selected companies")

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        self.history = DataTablePage(
            "Scan history",
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
            filters=(
                ("Status", "status", ("completed", "completed_with_errors", "failed")),
            ),
        )
        history_layout.addWidget(self.history)
        tabs.addTab(history_page, "History")
        self.refresh()

    def refresh(self) -> None:
        runs = list_scan_runs(self._database_path)
        latest = runs[0] if runs else None
        values = (
            latest.get("companies_scanned", 0) if latest else 0,
            latest.get("jobs_collected", 0) if latest else 0,
            latest.get("jobs_new", 0) if latest else 0,
            latest.get("jobs_changed", 0) if latest else 0,
            latest.get("review_needed_count", 0) if latest else 0,
            latest.get("collector_errors", 0) if latest else 0,
        )
        for card, value in zip(self.receipt_cards, values, strict=True):
            card[1].setText(str(value or 0))
        self.problems.clear()
        errors = (
            list_scan_errors(self._database_path, int(latest["id"]) if latest else None)
            if latest
            else ()
        )
        for error in errors:
            self.problems.addItem(
                f"{error.get('company') or error.get('company_key')} "
                f"({error.get('source_type')}): {error.get('message')}"
            )
        if not errors:
            self.problems.addItem(
                "No company-source problems were recorded for the latest scan."
                if latest
                else "No completed scan information is available yet."
            )
        self.company_choices.clear()
        for company in list_companies(self._database_path):
            if not company.get("enabled"):
                continue
            choice = QListWidgetItem(
                f"{company['name']} — {company['source_type']}", self.company_choices
            )
            choice.setData(Qt.ItemDataRole.UserRole, company["company_key"])
            choice.setCheckState(Qt.CheckState.Unchecked)
        self.history.refresh()

    def set_running(self, running: bool) -> None:
        self.run_button.setDisabled(running)
        self.run_button.setText("Scan running…" if running else "Run scan")
        self.progress.setVisible(running)
        self.stage.setText(
            "Collecting and evaluating enabled company sources…"
            if running
            else "No scan is currently running."
        )

    def _check_all(self, checked: bool) -> None:
        state = Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked
        for index in range(self.company_choices.count()):
            self.company_choices.item(index).setCheckState(state)

    def _start_selected(self) -> None:
        keys = tuple(
            str(item.data(Qt.ItemDataRole.UserRole))
            for index in range(self.company_choices.count())
            if (item := self.company_choices.item(index)).checkState()
            == Qt.CheckState.Checked
        )
        if keys:
            self._run_selected(keys)


class CompaniesPage(QWidget):
    """Native company catalog, profile assignment, and source-health workspace."""

    def __init__(
        self,
        database_path: Path,
        add_company: Callable[[dict[str, object] | None], None],
        edit_company: Callable[[dict[str, object] | None], None],
        toggle_company: Callable[[dict[str, object] | None], None],
        import_catalog: Callable[[], None],
        test_sources: Callable[[tuple[str, ...]], None],
    ) -> None:
        super().__init__()
        self._database_path = database_path
        self._test_sources = test_sources
        layout = QVBoxLayout(self)
        heading = QLabel("Companies")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        intro = QLabel(
            "Choose which employers Junior scans for the active profile and verify "
            "that their public recruiting sources remain readable."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        tabs = self.tabs = QTabWidget()
        layout.addWidget(tabs, 1)
        self.catalog = DataTablePage(
            "Your companies",
            ("Key", "Company", "Source", "URL", "Scanning", "Updated"),
            lambda: list_companies(self._database_path),
            actions=(
                ("Add company…", add_company),
                ("Edit…", edit_company),
                ("Enable / disable", toggle_company),
            ),
            summary_metrics=(
                ("Available", lambda rows: len(rows)),
                ("Scanning", lambda rows: _count(rows, "enabled", 1)),
                ("Not scanning", lambda rows: _count(rows, "enabled", 0)),
                (
                    "Platforms",
                    lambda rows: len({row.get("source_type") for row in rows}),
                ),
            ),
            filters=(
                ("Source", "source_type", _collector_names()),
                ("Profile status", "enabled", ("1", "0")),
            ),
        )
        tabs.addTab(self.catalog, "Companies")

        health_page = QWidget()
        health_layout = QVBoxLayout(health_page)
        health_layout.addWidget(
            QLabel(
                "Connection tests read a small sample and do not import jobs. "
                "Actual collection belongs on the Scan page."
            )
        )
        health_controls = QHBoxLayout()
        self.test_untested = QPushButton("Test every source not tested yet")
        self.test_selected = QPushButton("Test checked sources")
        self.test_untested.clicked.connect(self._test_all_untested)
        self.test_selected.clicked.connect(self._test_checked)
        self.health_filter = QComboBox()
        self.health_filter.addItems(
            ("All companies", "Healthy", "Needs attention", "Not tested")
        )
        self.health_filter.currentTextChanged.connect(self._apply_health_filter)
        health_controls.addWidget(self.test_untested)
        health_controls.addWidget(self.test_selected)
        health_controls.addStretch(1)
        health_controls.addWidget(self.health_filter)
        health_layout.addLayout(health_controls)
        self.health_table = QTableWidget(0, 5)
        self.health_table.setHorizontalHeaderLabels(
            ("Test", "Company", "Platform", "Profile status", "Connection health")
        )
        self.health_table.horizontalHeader().setStretchLastSection(True)
        self.health_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        health_layout.addWidget(self.health_table, 1)
        tabs.addTab(health_page, "Source health")

        transfer_page = QWidget()
        transfer_layout = QVBoxLayout(transfer_page)
        transfer = QGroupBox("Import or export company catalog")
        transfer_form = QFormLayout(transfer)
        import_button = QPushButton("Append missing companies…")
        import_button.clicked.connect(import_catalog)
        export_button = QPushButton("Export companies…")
        export_button.clicked.connect(self._export_catalog)
        transfer_form.addRow(
            "Import adds missing companies without replacing existing settings.",
            import_button,
        )
        transfer_form.addRow(
            "Export the current portable company catalog.", export_button
        )
        transfer_layout.addWidget(transfer)
        transfer_layout.addStretch(1)
        tabs.addTab(transfer_page, "Import / export")
        self.refresh()

    def refresh(self) -> None:
        self.catalog.refresh()
        companies = list_companies(self._database_path)
        health = {
            str(row["company_key"]): row
            for row in list_company_source_health(self._database_path)
        }
        self.health_table.setRowCount(len(companies))
        for row_index, company in enumerate(companies):
            check = QTableWidgetItem()
            check.setCheckState(Qt.CheckState.Unchecked)
            check.setData(Qt.ItemDataRole.UserRole, company["company_key"])
            state = health.get(str(company["company_key"]))
            values = (
                company["name"],
                company["source_type"],
                "Scanning" if company.get("enabled") else "Not scanning",
                str(state["state"]).replace("_", " ").title()
                if state
                else "Not tested",
            )
            self.health_table.setItem(row_index, 0, check)
            for column, value in enumerate(values, 1):
                self.health_table.setItem(
                    row_index, column, QTableWidgetItem(str(value))
                )
        self.health_table.resizeColumnsToContents()
        self._apply_health_filter()

    def _apply_health_filter(self) -> None:
        selected = self.health_filter.currentText()
        for row in range(self.health_table.rowCount()):
            state = self.health_table.item(row, 4).text()
            visible = (
                selected == "All companies"
                or selected == state
                or (selected == "Needs attention" and state == "Needs Attention")
            )
            self.health_table.setRowHidden(row, not visible)

    def set_testing(self, testing: bool) -> None:
        self.test_untested.setDisabled(testing)
        self.test_selected.setDisabled(testing)
        self.test_untested.setText(
            "Testing company sources…"
            if testing
            else "Test every source not tested yet"
        )

    def _test_all_untested(self) -> None:
        tested = {
            str(row["company_key"])
            for row in list_company_source_health(self._database_path)
        }
        keys = tuple(
            str(row["company_key"])
            for row in list_companies(self._database_path)
            if str(row["company_key"]) not in tested
        )
        if keys:
            self._test_sources(keys)

    def _test_checked(self) -> None:
        keys = tuple(
            str(item.data(Qt.ItemDataRole.UserRole))
            for row in range(self.health_table.rowCount())
            if (item := self.health_table.item(row, 0)).checkState()
            == Qt.CheckState.Checked
        )
        if keys:
            self._test_sources(keys)

    def _export_catalog(self) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self, "Export companies", "junior-companies.json", "JSON files (*.json)"
        )
        if not destination:
            return
        Path(destination).write_text(
            json.dumps(list_companies(self._database_path), indent=2), encoding="utf-8"
        )


class HomePage(QWidget):
    def __init__(
        self,
        database_path: Path,
        navigate: Callable[[int, Callable[[dict[str, object]], bool] | None], None],
    ) -> None:
        super().__init__()
        self._database_path = database_path
        self._navigate = navigate
        layout = QVBoxLayout(self)
        heading = QLabel("Junior")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        layout.addWidget(QLabel("Local-first job discovery and application management"))
        self.setup_group = QGroupBox("Getting started")
        setup_layout = QVBoxLayout(self.setup_group)
        self.setup_steps = QListWidget()
        self.setup_steps.setAccessibleName("First-run setup progress")
        self.setup_steps.setMaximumHeight(150)
        setup_layout.addWidget(self.setup_steps)
        self.setup_action = QPushButton("Continue setup")
        self.setup_action.clicked.connect(self._continue_setup)
        setup_layout.addWidget(self.setup_action)
        layout.addWidget(self.setup_group)
        self.cards = QGridLayout()
        self.card_widgets = tuple(
            _status_card(caption)
            for caption in (
                "Tracked applications",
                "Needs action",
                "Needs review",
                "Active pipeline",
                "Application history",
                "Unreviewed jobs",
            )
        )
        for index, card in enumerate(self.card_widgets):
            self.cards.addWidget(card[0], index // 3, index % 3)
        def application_active(row: dict[str, object]) -> bool:
            return str(row.get("status")) not in {"rejected", "withdrawn"}

        def needs_action(row: dict[str, object]) -> bool:
            return row.get("workflow_state") in {
                "follow_up_due", "needs_date_review", "stale", "dormant"
            }
        destinations = (
            (5, None),
            (5, needs_action),
            (5, lambda row: row.get("workflow_state") == "needs_date_review"),
            (5, application_active),
            (6, None),
            (4, lambda row: row.get("status") in {None, "new"}),
        )
        for card, (page_index, predicate) in zip(
            self.card_widgets, destinations, strict=True
        ):
            card[0].clicked.connect(
                lambda index=page_index, test=predicate: navigate(index, test)
            )
        layout.addLayout(self.cards)
        latest = QGroupBox("Latest scan")
        latest_layout = QGridLayout(latest)
        self.latest_cards = tuple(
            _status_card(caption)
            for caption in (
                "Top matches",
                "Potential matches",
                "Location outliers",
                "Review needed",
            )
        )
        for index, card in enumerate(self.latest_cards):
            latest_layout.addWidget(card[0], 0, index)
        latest_destinations = (
            lambda row: row.get("recommendation") == "top_match",
            lambda row: row.get("recommended_action")
            in {"tailor_resume", "network_first"},
            lambda row: row.get("location_status")
            in {"conditional", "mixed", "outside"},
            lambda row: row.get("recommendation") == "review_needed",
        )
        for card, predicate in zip(
            self.latest_cards, latest_destinations, strict=True
        ):
            card[0].clicked.connect(lambda test=predicate: navigate(4, test))
        layout.addWidget(latest)
        attention = QGroupBox("Needs attention")
        attention_layout = QVBoxLayout(attention)
        self.attention = QListWidget()
        attention_layout.addWidget(self.attention)
        layout.addWidget(attention, 1)
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
        values = (
            counts["application_tracker"],
            attention,
            workflow.get("needs_date_review", 0),
            workflow.get("active_pipeline", 0),
            counts["job_history"],
            sum(
                1
                for row in list_jobs(self._database_path)
                if row.get("status") in {None, "new"}
            ),
        )
        for card, value in zip(self.card_widgets, values, strict=True):
            card[1].setText(f"{value:,}")
        evaluations = list_job_evaluations(self._database_path)
        latest_values = (
            sum(row["recommendation"] == "top_match" for row in evaluations),
            sum(
                row["recommended_action"] in {"tailor_resume", "network_first"}
                for row in evaluations
            ),
            sum(
                row["location_status"] in {"conditional", "mixed"}
                for row in evaluations
            ),
            sum(row["recommendation"] == "review_needed" for row in evaluations),
        )
        for card, value in zip(self.latest_cards, latest_values, strict=True):
            card[1].setText(f"{value:,}")
        self.attention.clear()
        for application in list_application_views(self._database_path):
            if application["workflow_state"] in {
                "follow_up_due",
                "needs_date_review",
                "stale",
                "dormant",
            }:
                self.attention.addItem(
                    f"{application['company_name']} — {application['role_title']} "
                    f"({str(application['workflow_state']).replace('_', ' ')})"
                )
        if not self.attention.count():
            self.attention.addItem("Nothing currently needs attention.")
        self._refresh_setup()

    def _refresh_setup(self) -> None:
        profile = get_candidate_profile(self._database_path)
        enabled_companies = tuple(
            company
            for company in list_companies(self._database_path)
            if company.get("enabled")
        )
        scan_complete = bool(list_scan_runs(self._database_path))
        states = (
            ("Create your candidate profile", profile is not None, 1),
            (
                "Import and review your résumé",
                bool(profile and profile.resume_normalized_text_path),
                1,
            ),
            (
                "Choose target work and job-fit preferences",
                bool(profile and profile.target_roles),
                1,
            ),
            ("Choose and test company sources", bool(enabled_companies), 2),
            ("Run your first scan", scan_complete, 3),
        )
        self.setup_steps.clear()
        next_page = 0
        next_label = "Setup complete"
        for label, complete, page_index in states:
            self.setup_steps.addItem(f"{'✓' if complete else '○'}  {label}")
            if not complete and next_page == 0:
                next_page = page_index
                next_label = label
        self.setup_action.setText(next_label)
        self.setup_action.setProperty("page_index", next_page)
        self.setup_action.setEnabled(next_page != 0)
        self.setup_group.setVisible(not all(state[1] for state in states))

    def _continue_setup(self) -> None:
        page_index = int(self.setup_action.property("page_index") or 0)
        if page_index:
            self._navigate(page_index, None)


class HelpPage(QWidget):
    def __init__(self, data_directory: Path) -> None:
        super().__init__()
        self._data_directory = data_directory
        layout = QVBoxLayout(self)
        heading = QLabel("Help & About")
        heading.setObjectName("pageHeading")
        layout.addWidget(heading)
        intro = QLabel(
            "Junior is a local-first job discovery and application-management app. "
            "Your profile, résumé, scan history, decisions, and tracker remain on "
            "this computer unless you explicitly export or email a report."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)
        topics = QTabWidget()
        content = {
            "What Junior does": (
                "Collects configured company sources, interprets requirements with "
                "the managed local model, applies deterministic policy, and keeps an "
                "auditable recommendation."
            ),
            "Getting started": (
                "Create or select a profile, add a résumé, save job preferences, "
                "choose companies, test sources, then run a scan."
            ),
            "Scans": (
                "Scans run against enabled companies. Source failures are isolated "
                "and retained in diagnostics instead of aborting the whole scan."
            ),
            "Reviewing jobs": (
                "Review evidence, recommendation reasons, compensation, location, "
                "history risk, and résumé fit before tracking or passing a role."
            ),
            "Settings & backups": (
                "Configure email, scheduling, retention, platform credentials, and "
                "diagnostics. Export profiles and reports for portable backups."
            ),
            "Privacy": (
                "The LLM is local. Network access occurs only when collecting public "
                "job sources or when you explicitly send email."
            ),
            "Troubleshooting": (
                "Run diagnostics, inspect source errors, verify the managed Ollama "
                "model, and use the data-directory path shown in Settings."
            ),
        }
        for title, text in content.items():
            page = QWidget()
            page_layout = QVBoxLayout(page)
            label = QLabel(text)
            label.setWordWrap(True)
            page_layout.addWidget(label)
            page_layout.addStretch(1)
            topics.addTab(page, title)
        layout.addWidget(topics, 1)
        about = QGroupBox("Installation details")
        about_layout = QFormLayout(about)
        about_layout.addRow("Version", QLabel(__version__))
        about_layout.addRow("Operating system", QLabel(platform.platform()))
        about_layout.addRow("Python runtime", QLabel(platform.python_version()))
        data_path = QLabel(str(self._data_directory))
        data_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        data_path.setWordWrap(True)
        about_layout.addRow("Local data directory", data_path)
        open_data = QPushButton("Open data directory")
        open_data.clicked.connect(
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(data_directory)))
        )
        about_layout.addRow("", open_data)
        layout.addWidget(about)


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
            "Review Jobs",
            "Applications",
            "History",
            "Reports",
            "Help",
            "Settings",
        ):
            self.navigation.addItem(label)
        self.pages = QStackedWidget()
        self.home_page = HomePage(self._database_path, self._navigate_from_home)
        self.pages.addWidget(self.home_page)
        profile = ProfilePage(self._database_path, Path(data_directory))
        profile.saved.connect(self.statusBar().showMessage)
        self.pages.addWidget(profile)
        self.scan_page = ScanPage(
            self._database_path,
            lambda: self._run_scan(),
            self._run_scan,
        )
        self.data_pages = (
            CompaniesPage(
                self._database_path,
                self._add_company,
                self._edit_company,
                self._toggle_company,
                self._import_company_config,
                self._test_company_sources,
            ),
            self.scan_page,
            DataTablePage(
                "Review Jobs",
                (
                    "ID",
                    "Company",
                    "Title",
                    "Location",
                    "Workplace",
                    "Decision",
                    "Recommendation",
                    "Action",
                    "Score",
                    "Location fit",
                    "Seen",
                ),
                lambda: list_review_jobs(self._database_path),
                actions=(
                    ("Evaluate", self._evaluate_job),
                    ("Track application", self._track_job),
                    ("Set status…", self._set_job_status),
                ),
                summary_metrics=(
                    (
                        "Top matches",
                        lambda rows: _count(rows, "recommendation", "top_match"),
                    ),
                    (
                        "Potential matches",
                        lambda rows: sum(
                            row.get("recommended_action")
                            in {"tailor_resume", "network_first"}
                            for row in rows
                        ),
                    ),
                    (
                        "Needs review",
                        lambda rows: _count(rows, "recommendation", "review_needed"),
                    ),
                    (
                        "Outside locations",
                        lambda rows: sum(
                            row.get("location_status")
                            in {"conditional", "mixed", "outside"}
                            for row in rows
                        ),
                    ),
                    ("New this scan", lambda rows: _count(rows, "status", "new")),
                    (
                        "Saved & passed",
                        lambda rows: sum(
                            row.get("status") in {"saved", "passed"} for row in rows
                        ),
                    ),
                ),
                filters=(
                    ("Status", "status", ("new", "saved", "passed", "applied")),
                    (
                        "Recommendation",
                        "recommendation",
                        ("top_match", "review_needed", "omit"),
                    ),
                    ("Workplace", "remote_status", ("remote", "hybrid", "onsite")),
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
                summary_metrics=(
                    ("Tracked", lambda rows: len(rows)),
                    (
                        "Active",
                        lambda rows: sum(
                            str(row.get("status")) not in {"rejected", "withdrawn"}
                            for row in rows
                        ),
                    ),
                    (
                        "Follow-up due",
                        lambda rows: _count(rows, "workflow_state", "follow_up_due"),
                    ),
                    ("Interviews", lambda rows: _count(rows, "status", "interviewing")),
                ),
                filters=(
                    (
                        "Status",
                        "status",
                        (
                            "review_needed",
                            "saved",
                            "applied",
                            "interviewing",
                            "offer",
                            "withdrawn",
                            "rejected",
                        ),
                    ),
                    (
                        "Attention",
                        "workflow_state",
                        (
                            "follow_up_due",
                            "needs_date_review",
                            "stale",
                            "dormant",
                            "active",
                        ),
                    ),
                    (
                        "Outcome",
                        "outcome",
                        ("Pending / In Progress", "Offer", "Rejected", "Withdrawn"),
                    ),
                ),
                sorts=(
                    ("Recent activity", "last_activity_on", True),
                    ("Follow-up date", "follow_up_on", False),
                    ("Company A–Z", "company_name", False),
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
                summary_metrics=(
                    ("Historical records", lambda rows: len(rows)),
                    ("Included", lambda rows: _count(rows, "included", 1)),
                    ("Rejected", lambda rows: _count(rows, "status", "rejected")),
                    (
                        "Revisit",
                        lambda rows: sum(bool(row.get("revisit")) for row in rows),
                    ),
                ),
                filters=(
                    (
                        "Status",
                        "status",
                        ("applied", "interviewing", "offer", "rejected", "withdrawn"),
                    ),
                    ("Included", "included", ("1", "0")),
                ),
                sorts=(
                    ("Newest first", "event_date", True),
                    ("Oldest first", "event_date", False),
                    ("Company A–Z", "company", False),
                    ("Role A–Z", "role", False),
                ),
            ),
            ReportsPage(
                self._database_path,
                self._export_report,
                self._save_email_preview,
                self._send_email,
            ),
        )
        self.applications_page = self.data_pages[3]
        self.review_page = self.data_pages[2]
        self.review_page.add_summary_quick_filters(
            (
                lambda row: row.get("recommendation") == "top_match",
                lambda row: row.get("recommended_action")
                in {"tailor_resume", "network_first"},
                lambda row: row.get("recommendation") == "review_needed",
                lambda row: row.get("location_status")
                in {"conditional", "mixed", "outside"},
                lambda row: row.get("status") == "new",
                lambda row: row.get("status") in {"saved", "passed"},
            )
        )
        self.applications_page.add_bulk_action(
            "Update selected…", self._bulk_application_action
        )
        for page in self.data_pages:
            self.pages.addWidget(page)
        self.pages.addWidget(HelpPage(self._data_directory))
        self.settings_page = EmailSettingsPage(
            self._settings,
            self._database_path,
            self._data_directory,
            self._test_company_sources,
        )
        self.settings_page.saved.connect(self.statusBar().showMessage)
        self.pages.addWidget(self.settings_page)
        self.navigation.currentRowChanged.connect(self._show_page)
        self.navigation.setCurrentRow(0)
        layout.addWidget(self.navigation)
        layout.addWidget(self.pages, 1)
        self.setCentralWidget(root)
        self._build_menu()
        self.setStyleSheet(_STYLE)

    def _navigate_from_home(
        self,
        page_index: int,
        predicate: Callable[[dict[str, object]], bool] | None,
    ) -> None:
        self.navigation.setCurrentRow(page_index)
        page = self.pages.widget(page_index)
        if isinstance(page, DataTablePage):
            page.set_quick_filter(predicate)

    def _show_page(self, page_index: int) -> None:
        self.pages.setCurrentIndex(page_index)
        page = self.pages.widget(page_index)
        if page is self.home_page:
            self.home_page.refresh()
        elif isinstance(page, DataTablePage):
            page.refresh()

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

    def _run_scan(self, company_keys: tuple[str, ...] | None = None) -> None:
        registry = _collector_registry()
        self.statusBar().showMessage("Scanning enabled companies…")
        self.scan_page.set_running(True)
        self._scan_task = ScanTask(
            ScanService(
                self._database_path,
                registry,
                qualification_runner=self._qualification_runner,
                resume_runner=self._resume_runner,
                company_keys=company_keys,
            )
        )
        self._scan_task.signals.finished.connect(self._scan_finished)
        self._scan_task.signals.failed.connect(self._scan_failed)
        QThreadPool.globalInstance().start(self._scan_task)

    def _test_company_sources(self, company_keys: tuple[str, ...]) -> None:
        if not company_keys:
            self.statusBar().showMessage("Select at least one company source.")
            return
        self.statusBar().showMessage(f"Testing {len(company_keys)} company source(s)…")
        self.data_pages[0].set_testing(True)
        self._source_test_task = SourceTestTask(self._database_path, company_keys)
        self._source_test_task.signals.finished.connect(self._source_tests_finished)
        self._source_test_task.signals.failed.connect(self._scan_failed)
        QThreadPool.globalInstance().start(self._source_test_task)

    def _source_tests_finished(self, results: object) -> None:
        self.data_pages[0].set_testing(False)
        self.data_pages[0].refresh()
        rows = tuple(results) if isinstance(results, tuple) else ()
        failures = sum(row[1] != "healthy" for row in rows)
        self.statusBar().showMessage(
            f"Source testing finished: {len(rows)} checked, {failures} need attention."
        )

    def _scan_finished(self, summary: ScanSummary) -> None:
        self.scan_page.set_running(False)
        self.scan_page.refresh()
        self.data_pages[2].refresh()
        self.statusBar().showMessage(
            f"Scan {summary.run_id} complete: {summary.jobs_collected} jobs, "
            f"{summary.jobs_new} new, {summary.errors} errors."
        )

    def _scan_failed(self, message: str) -> None:
        self.scan_page.set_running(False)
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

    def _bulk_application_action(self, rows: tuple[dict[str, object], ...]) -> None:
        if not rows:
            self.statusBar().showMessage("Select one or more applications first.")
            return
        options = {
            "Schedule follow-up next week": "follow_up_next_week",
            "Mark follow-up due": "follow_up_due",
            "Mark dormant": "dormant",
            "Mark interview scheduled": "interview_scheduled",
            "Mark waiting for feedback": "waiting_for_feedback",
        }
        label, accepted = QInputDialog.getItem(
            self,
            "Update selected applications",
            "Action",
            tuple(options),
            editable=False,
        )
        if not accepted:
            return
        selected_ids = {str(row["job_radar_id"]) for row in rows}
        applications = {
            item.job_radar_id: item for item in list_applications(self._database_path)
        }
        updated = 0
        for job_id in selected_ids:
            if application := applications.get(job_id):
                save_application(
                    self._database_path,
                    apply_quick_action(application, options[label]),
                )
                updated += 1
        self.applications_page.refresh()
        self.home_page.refresh()
        self.statusBar().showMessage(f"Updated {updated} applications.")

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


def _money(value: int | None) -> str:
    return f"${value:,}" if value else "Not configured"


class _StatusCard(QFrame):
    clicked = Signal()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()
        super().mouseReleaseEvent(event)


def _status_card(caption: str) -> tuple[_StatusCard, QLabel]:
    card = _StatusCard()
    card.setObjectName("card")
    layout = QVBoxLayout(card)
    value = QLabel("Not configured")
    value.setObjectName("cardValue")
    value.setWordWrap(True)
    label = QLabel(caption)
    label.setObjectName("muted")
    layout.addWidget(value)
    layout.addWidget(label)
    return card, value


def _multi_choice(options: tuple[str, ...]) -> QListWidget:
    control = QListWidget()
    control.addItems(options)
    control.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
    control.setMaximumHeight(112)
    return control


def _selected_choices(control: QListWidget) -> tuple[str, ...]:
    return tuple(item.text() for item in control.selectedItems())


def _select_choices(control: QListWidget, values: tuple[str, ...]) -> None:
    selected = set(values)
    for index in range(control.count()):
        item = control.item(index)
        item.setSelected(item.text() in selected)


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


def _append_unique_line(control: QTextEdit, value: str) -> None:
    values = list(_lines(control))
    if value and value.casefold() not in {item.casefold() for item in values}:
        values.append(value)
        control.setPlainText("\n".join(values))


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
        summary_metrics: tuple[
            tuple[str, Callable[[tuple[dict[str, object], ...]], int]], ...
        ] = (),
        filters: tuple[tuple[str, str, tuple[str, ...]], ...] = (),
        sorts: tuple[tuple[str, str, bool], ...] = (),
    ) -> None:
        super().__init__()
        self._loader = loader
        self._all_rows: tuple[dict[str, object], ...] = ()
        self._rows: tuple[dict[str, object], ...] = ()
        self._quick_filter: Callable[[dict[str, object]], bool] | None = None
        layout = QVBoxLayout(self)
        heading_row = self.heading_row = QHBoxLayout()
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
        self.summary_cards = tuple(
            (caption, counter, _status_card(caption))
            for caption, counter in summary_metrics
        )
        if self.summary_cards:
            cards = QHBoxLayout()
            for _caption, _counter, card in self.summary_cards:
                cards.addWidget(card[0])
            layout.addLayout(cards)
        filter_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(f"Search {name.casefold()}…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self.search, 2)
        self.filters: list[tuple[str, QComboBox]] = []
        for label, key, choices in filters:
            control = QComboBox()
            control.setAccessibleName(label)
            control.addItem(f"All {label.casefold()}", None)
            for choice in choices:
                control.addItem(choice.replace("_", " ").title(), choice)
            control.currentIndexChanged.connect(self._apply_filter)
            filter_row.addWidget(control)
            self.filters.append((key, control))
        self.sort_control: QComboBox | None = None
        self._sorts = sorts
        if sorts:
            self.sort_control = QComboBox()
            self.sort_control.setAccessibleName("Sort")
            for label, key, reverse in sorts:
                self.sort_control.addItem(label, (key, reverse))
            self.sort_control.currentIndexChanged.connect(self._apply_filter)
            filter_row.addWidget(self.sort_control)
        layout.addLayout(filter_row)
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.setAlternatingRowColors(True)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setMinimumSectionSize(90)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table, 1)
        self.refresh()

    def add_bulk_action(
        self,
        label: str,
        callback: Callable[[tuple[dict[str, object], ...]], None],
    ) -> None:
        button = QPushButton(label)
        button.clicked.connect(lambda: callback(self.selected_rows()))
        self.heading_row.insertWidget(self.heading_row.count() - 1, button)

    def add_summary_quick_filters(
        self,
        predicates: tuple[Callable[[dict[str, object]], bool] | None, ...],
    ) -> None:
        if len(predicates) != len(self.summary_cards):
            raise ValueError("Each summary card requires one quick filter.")
        for (_caption, _counter, card), predicate in zip(
            self.summary_cards, predicates, strict=True
        ):
            card[0].clicked.connect(
                lambda test=predicate: self.set_quick_filter(test)
            )

    def refresh(self) -> None:
        self._all_rows = self._loader()
        for _caption, counter, card in self.summary_cards:
            card[1].setText(f"{counter(self._all_rows):,}")
        self._apply_filter()

    def set_quick_filter(
        self, predicate: Callable[[dict[str, object]], bool] | None
    ) -> None:
        self._quick_filter = predicate
        self.search.clear()
        for _key, control in self.filters:
            control.setCurrentIndex(0)
        self._apply_filter()

    def _apply_filter(self) -> None:
        needle = self.search.text().strip().casefold()
        rows = tuple(
            row
            for row in self._all_rows
            if not needle
            or needle in " ".join(str(value or "") for value in row.values()).casefold()
        )
        if self._quick_filter is not None:
            rows = tuple(row for row in rows if self._quick_filter(row))
        for key, control in self.filters:
            selected = control.currentData()
            if selected is not None:
                rows = tuple(
                    row
                    for row in rows
                    if str(row.get(key) or "").casefold() == str(selected).casefold()
                )
        if self.sort_control is not None:
            key, reverse = self.sort_control.currentData()
            rows = tuple(
                sorted(
                    rows,
                    key=lambda row: str(row.get(key) or "").casefold(),
                    reverse=bool(reverse),
                )
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

    def selected_rows(self) -> tuple[dict[str, object], ...]:
        indexes = sorted({item.row() for item in self.table.selectedItems()})
        rows = []
        for row in indexes:
            item = self.table.item(row, 0)
            source_row = item.data(Qt.ItemDataRole.UserRole) if item else None
            if source_row is not None and 0 <= int(source_row) < len(self._rows):
                rows.append(self._rows[int(source_row)])
        return tuple(rows)


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


class SourceTestTask(QRunnable):
    def __init__(self, database_path: Path, company_keys: tuple[str, ...]) -> None:
        super().__init__()
        self._database_path = database_path
        self._company_keys = company_keys
        self.signals = ScanSignals()

    def run(self) -> None:
        registry = _collector_registry()
        results = []
        for company_key in self._company_keys:
            company = get_company(self._database_path, company_key)
            if company is None:
                continue
            settings = dict(company.get("source_settings") or {})
            settings["source_slug"] = company.get("source_slug")
            settings["source_url"] = company.get("source_url")
            source = CollectorSource(
                company_key,
                str(company["name"]),
                str(company["source_type"]),
                settings,
            )
            try:
                jobs = registry.collector_for(source.source_type).collect(source)
                state = "healthy"
                message = f"Connection succeeded; {len(jobs)} jobs returned."
                count = len(jobs)
            except Exception as error:
                state = "needs_attention"
                message = str(error)
                count = None
            save_company_source_health(
                self._database_path, company_key, state, message, count
            )
            results.append((company_key, state, message, count))
        self.signals.finished.emit(tuple(results))


def _slug(value: str) -> str:
    return "-".join(value.lower().split())


def _optional_text(value: object) -> str | None:
    text = str(value or "").strip()
    return text or None


def _count(rows: tuple[dict[str, object], ...], key: str, expected: object) -> int:
    return sum(
        str(row.get(key) or "").casefold() == str(expected).casefold() for row in rows
    )


def _collector_names() -> tuple[str, ...]:
    return (
        "activate",
        "adp",
        "ashby",
        "dayforce",
        "greenhouse",
        "html",
        "icims",
        "jibe",
        "jobsyn",
        "lever",
        "oracle_hcm",
        "phenom",
        "rippling",
        "schoolspring",
        "selectminds",
        "smartrecruiters",
        "usajobs",
        "weka",
        "workday",
    )


def _collector_registry() -> CollectorRegistry:
    return CollectorRegistry(
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


_STYLE = """
QMainWindow, QWidget { background: #12161c; color: #eef3f8; font-size: 14px; }
QLabel, QCheckBox { background: transparent; }
#navigation { background: #18202a; border: 0; padding: 18px 8px; }
#navigation::item { padding: 13px 14px; border-radius: 6px; }
#navigation::item:selected { background: #175f89; }
#pageHeading { font-size: 28px; font-weight: 700; margin: 20px 8px 8px 8px; }
#summary, #card { background: #1c242e; border: 1px solid #344250;
  border-radius: 8px; padding: 18px; }
#cardValue { font-size: 20px; font-weight: 700; }
#muted { color: #aeb9c5; }
QGroupBox { border: 1px solid #344250; border-radius: 8px; margin-top: 12px;
  padding: 18px 12px 12px 12px; font-weight: 700; }
QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }
QTabWidget::pane { border: 1px solid #344250; border-radius: 8px; }
QTabBar::tab { background: #1c242e; padding: 9px 16px; margin-right: 4px;
  border-top-left-radius: 7px; border-top-right-radius: 7px; }
QTabBar::tab:selected { background: #175f89; }
QLineEdit, QSpinBox, QTextEdit { background: #202832; border: 1px solid #465463;
  border-radius: 4px; padding: 7px; }
QPushButton { padding: 8px 14px; }
#primaryButton { background: #1878ac; border-radius: 5px; }
QStatusBar { background: #18202a; }
"""
