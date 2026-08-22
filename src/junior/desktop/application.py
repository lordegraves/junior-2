"""Create and run Junior's native Qt application."""

import sys
from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from junior.application.interpret_qualification_review import (
    InterpretQualificationReview,
)
from junior.application.interpret_resume_review import InterpretResumeReview
from junior.application.review_fixtures import load_review_fixtures
from junior.desktop.review_window import QualificationReviewWindow
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
    window = QualificationReviewWindow(
        load_review_fixtures(),
        interpretation_runner=_interpret_with_ollama,
        resume_interpretation_runner=_interpret_resume_with_ollama,
    )
    window.show()
    return app.exec()
