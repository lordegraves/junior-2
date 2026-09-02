"""Create and run Junior's native Qt application."""

import os
import sys
from collections.abc import Sequence

from PySide6.QtCore import QSettings, QStandardPaths, Qt
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
