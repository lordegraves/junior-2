"""Create and run Junior's native Qt application."""

import os
import sys
from collections.abc import Sequence

from PySide6.QtCore import QCoreApplication, QSettings, QStandardPaths, Qt
from PySide6.QtWidgets import QApplication

from junior.application.interpret_qualification_review import (
    InterpretQualificationReview,
)
from junior.application.interpret_resume_review import InterpretResumeReview
from junior.application.review_fixtures import load_review_fixtures
from junior.desktop.main_window import JuniorMainWindow
from junior.desktop.review_window import QualificationReviewWindow
from junior.infrastructure.application_database import initialize_database
from junior.infrastructure.ollama_qualification_backend import (
    OllamaQualificationBackend,
)
from junior.interpretation.qualification_evidence_validator import (
    QualificationEvidenceValidator,
)
from junior.reporting.email_sender import send_email_report
from junior.reporting.scan_report import render_html_report, render_markdown_report


def _interpret_with_ollama(
    model_name: str,
    title: str,
    company: str,
    content: str,
    source_uri: str | None,
):
    service = InterpretQualificationReview(
        backend=OllamaQualificationBackend(model_id=model_name),
        validator=QualificationEvidenceValidator(),
    )
    return service.execute(
        title=title,
        company=company,
        content=content,
        source_uri=source_uri,
    )


def _interpret_resume_with_ollama(
    model_name: str,
    filename: str,
    content: str,
):
    service = InterpretResumeReview(
        backend=OllamaQualificationBackend(model_id=model_name),
        validator=QualificationEvidenceValidator(),
    )
    return service.execute(filename=filename, content=content)


def run_desktop_application(arguments: Sequence[str] | None = None) -> int:
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(list(arguments) if arguments is not None else sys.argv)
    app.setApplicationName("Junior 2.0")
    app.setOrganizationName("Junior")
    data_directory = os.environ.get(
        "JUNIOR_DATA_DIR"
    ) or QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    if not data_directory:
        raise RuntimeError("Junior could not determine a writable user-data directory.")
    database_path = initialize_database(f"{data_directory}/junior-2.sqlite3")
    settings = QSettings()
    _apply_source_credentials(settings)

    def create_workbench(
        job: dict[str, object] | None = None,
    ) -> QualificationReviewWindow:
        window = QualificationReviewWindow(
            load_review_fixtures(),
            interpretation_runner=_interpret_with_ollama,
            resume_interpretation_runner=_interpret_resume_with_ollama,
            settings=settings,
            database_path=database_path,
        )
        if job is not None:
            window.load_posting(
                company=str(job.get("company") or ""),
                title=str(job.get("title") or ""),
                content=str(job.get("description") or ""),
                source_uri=str(job.get("source_url") or "") or None,
            )
        return window

    window = JuniorMainWindow(
        database_path=database_path,
        data_directory=data_directory,
        settings=settings,
        workbench_factory=create_workbench,
        qualification_runner=lambda **values: _interpret_with_ollama(
            "qwen2.5:3b", **values
        ),
        resume_runner=lambda **values: _interpret_resume_with_ollama(
            "qwen2.5:3b", **values
        ),
    )
    window.show()
    return app.exec()


def run_scheduled_scan() -> int:
    """Run the installed application's scan workflow without opening a window."""
    app = QCoreApplication.instance() or QCoreApplication(
        ["junior", "--scheduled-scan"]
    )
    app.setApplicationName("Junior 2.0")
    app.setOrganizationName("Junior")
    data_directory = os.environ.get(
        "JUNIOR_DATA_DIR"
    ) or QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.AppDataLocation
    )
    if not data_directory:
        raise RuntimeError("Junior could not determine its user-data directory.")
    database_path = initialize_database(f"{data_directory}/junior-2.sqlite3")
    settings = QSettings()
    _apply_source_credentials(settings)
    from junior.application.scan_service import ScanService
    from junior.desktop.main_window import _collector_registry

    summary = ScanService(
        database_path,
        _collector_registry(),
        qualification_runner=lambda **values: _interpret_with_ollama(
            "qwen2.5:3b", **values
        ),
        resume_runner=lambda **values: _interpret_resume_with_ollama(
            "qwen2.5:3b", **values
        ),
    ).run()
    if settings.value("schedule/email_delivery", False, bool):
        recipients = settings.value("email/recipients", "", str)
        values = {
            "enabled": settings.value("email/enabled", False, bool),
            "provider": settings.value("email/provider", "Custom SMTP", str),
            "sender": settings.value("email/sender", "", str),
            "sender_name": settings.value("email/sender_name", "Junior", str),
            "recipients": [
                item.strip() for item in recipients.split(",") if item.strip()
            ],
            "smtp_host": settings.value("email/smtp_host", "", str),
            "smtp_port": settings.value("email/smtp_port", 587, int),
            "smtp_username": settings.value("email/smtp_username", "", str),
            "smtp_password_env": settings.value(
                "email/smtp_password_env", "JUNIOR_SMTP_PASSWORD", str
            ),
            "smtp_tls_mode": settings.value("email/smtp_tls_mode", "starttls", str),
        }
        result = send_email_report(
            values,
            "Junior 2.0 scheduled scan report",
            render_markdown_report(database_path),
            render_html_report(database_path),
        )
        if not result.sent:
            return 2
    return 0 if summary.errors == 0 else 1


def _apply_source_credentials(settings: QSettings) -> None:
    """Map secret references to the environment expected by collectors."""
    email = settings.value("usajobs/email", "", str).strip()
    key_variable = settings.value(
        "usajobs/api_key_env", "USAJOBS_API_KEY", str
    ).strip()
    if email:
        os.environ["USAJOBS_USER_AGENT"] = email
    if key_variable and (key := os.environ.get(key_variable)):
        os.environ["USAJOBS_AUTHORIZATION_KEY"] = key
