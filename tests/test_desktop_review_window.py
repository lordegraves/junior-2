import os
from dataclasses import replace
from time import monotonic
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QFileDialog, QTreeWidgetItem

from junior.application.evaluation_sample import EvaluationPosting, EvaluationSample
from junior.application.interpret_qualification_review import (
    QualificationFailureCode,
    QualificationInterpretationError,
)
from junior.application.review_fixtures import load_review_fixtures
from junior.application.review_workspace import (
    QualificationGroupReview,
    QualificationPathReview,
    ReviewWorkspaceResult,
)
from junior.desktop.review_window import QualificationReviewWindow
from junior.domain.qualifications import RequirementPriority


def _application() -> QApplication:
    return QApplication.instance() or QApplication([])


def _first_requirement(item: QTreeWidgetItem) -> QTreeWidgetItem | None:
    for child_index in range(item.childCount()):
        child = item.child(child_index)
        if child.childCount() == 0 and child.text(1):
            return child
        found = _first_requirement(child)
        if found is not None:
            return found
    return None


def test_window_renders_alternatives_and_highlights_selected_evidence() -> None:
    _application()
    window = QualificationReviewWindow(load_review_fixtures())
    window.fixture_picker.setCurrentIndex(1)

    assert window.fixture_picker.count() == 5
    assert window.qualification_tree.topLevelItemCount() == 2
    first_group = window.qualification_tree.topLevelItem(0)
    assert "meet any one option" in first_group.text(0).casefold()

    requirement = _first_requirement(first_group)
    assert requirement is not None
    window.qualification_tree.setCurrentItem(requirement)
    QApplication.processEvents()

    assert len(window.source_text.extraSelections()) == 1
    assert window.technical_details.isHidden()
    window.close()


def test_window_clearly_displays_rejected_fixture() -> None:
    _application()
    window = QualificationReviewWindow(load_review_fixtures())
    rejected_index = window.fixture_picker.findData("fixture-rejected")

    window.fixture_picker.setCurrentIndex(rejected_index)
    QApplication.processEvents()

    assert not window.rejected_box.isHidden()
    assert window.rejected_list.count() == 1
    assert "rejected" in window.validation_heading.text().casefold()
    window.close()


def test_interactive_workspace_requires_posting_text() -> None:
    _application()
    window = QualificationReviewWindow(load_review_fixtures(), lambda *args: None)

    assert not window.source_text.isReadOnly()
    window.interpret_button.click()

    assert "paste a complete job posting" in (
        window.interpretation_status.text().casefold()
    )
    window.close()


def test_interactive_workspace_runs_off_the_ui_thread() -> None:
    app = _application()
    expected = load_review_fixtures()[2]

    def runner(*args: str) -> ReviewWorkspaceResult:
        return expected

    window = QualificationReviewWindow(load_review_fixtures(), runner)
    window.source_text.setPlainText("A complete posting")
    window.interpret_button.click()
    deadline = monotonic() + 2
    while window._worker_thread is not None and monotonic() < deadline:
        app.processEvents()

    assert window._worker_thread is None
    assert "completed" in window.interpretation_status.text().casefold()
    assert window.statusBar().currentMessage() == "Reviewed example loaded"
    window.close()


def test_interactive_workspace_preserves_safe_failure_reason() -> None:
    app = _application()

    def runner(*args: str) -> ReviewWorkspaceResult:
        raise QualificationInterpretationError(
            QualificationFailureCode.CONTRACT_INVALID_VALUE,
            "Safe contract failure",
        )

    window = QualificationReviewWindow(load_review_fixtures(), runner)
    window.source_text.setPlainText("A complete posting")
    window.interpret_button.click()
    deadline = monotonic() + 2
    while window._worker_thread is not None and monotonic() < deadline:
        app.processEvents()

    assert "Safe contract failure" in window.interpretation_status.text()
    assert "contract_invalid_value" in window.interpretation_status.text()
    assert "not accepted" in window.validation_heading.text().casefold()
    window.close()


def test_window_imports_rc6_sample_into_input_picker() -> None:
    _application()
    sample = EvaluationSample(
        source_build="RC6 Build 1.25",
        jobs_in_export=100,
        eligible_jobs=80,
        postings=(
            EvaluationPosting(
                posting_id="jr-example-1",
                company="Example",
                title="Systems Engineer",
                description="Public Trust clearance required.",
                source_url="https://example.invalid/jobs/1",
                sample_category="clearance or work authorization",
            ),
        ),
    )
    window = QualificationReviewWindow(load_review_fixtures())

    with (
        patch.object(QFileDialog, "getOpenFileName", return_value=("scan.zip", "")),
        patch(
            "junior.desktop.review_window.import_rc6_evaluation_sample",
            return_value=sample,
        ),
    ):
        window.import_button.click()

    assert window.fixture_picker.count() == 6
    assert window.company_input.text() == "Example"
    assert window.title_input.text() == "Systems Engineer"
    assert window.source_text.toPlainText() == "Public Trust clearance required."
    assert window._current_source_uri == "https://example.invalid/jobs/1"
    assert window.batch_button.isEnabled()
    assert not window.batch_box.isHidden()
    window.close()


def test_window_imports_resume_and_runs_review_off_ui_thread() -> None:
    app = _application()
    expected = replace(
        load_review_fixtures()[1],
        company="Resume",
        title="resume.txt",
        document_kind="resume",
    )

    def resume_runner(*args: str) -> ReviewWorkspaceResult:
        return expected

    window = QualificationReviewWindow(
        load_review_fixtures(),
        resume_interpretation_runner=resume_runner,
    )
    with (
        patch.object(
            QFileDialog,
            "getOpenFileName",
            return_value=("resume.txt", ""),
        ),
        patch(
            "junior.desktop.review_window.import_resume_text",
            return_value="Built Python services",
        ),
    ):
        window.resume_button.click()

    assert window.source_box.title() == "Original resume"
    assert window.source_text.toPlainText() == "Built Python services"
    assert window.interpret_button.text() == "Interpret resume"
    window.interpret_button.click()
    deadline = monotonic() + 2
    while window._worker_thread is not None and monotonic() < deadline:
        app.processEvents()

    assert window._worker_thread is None
    assert "completed" in window.interpretation_status.text().casefold()
    assert window.source_box.title() == "Original resume"
    window.close()


def test_window_runs_imported_sample_and_opens_completed_result() -> None:
    app = _application()
    fixture = load_review_fixtures()[1]
    postings = tuple(
        EvaluationPosting(
            posting_id=f"jr-example-{number}",
            company=f"Example {number}",
            title=f"Systems Engineer {number}",
            description="Public Trust clearance required.",
            source_url=f"https://example.invalid/jobs/{number}",
            sample_category="clearance or work authorization",
        )
        for number in (1, 2)
    )
    sample = EvaluationSample(
        source_build="RC6 Build 1.25",
        jobs_in_export=100,
        eligible_jobs=80,
        postings=postings,
    )

    def runner(_model, title, company, _content, _source_url):
        return replace(fixture, company=company, title=title)

    window = QualificationReviewWindow(load_review_fixtures(), runner)
    with (
        patch.object(QFileDialog, "getOpenFileName", return_value=("scan.zip", "")),
        patch(
            "junior.desktop.review_window.import_rc6_evaluation_sample",
            return_value=sample,
        ),
    ):
        window.import_button.click()

    window.batch_button.click()
    deadline = monotonic() + 2
    while window._worker_thread is not None and monotonic() < deadline:
        app.processEvents()

    assert window._worker_thread is None
    assert window.batch_results.topLevelItemCount() == 2
    assert "2 processed" in window.batch_status.text()
    assert "2 evidence verified" in window.batch_status.text()
    assert window.batch_results.topLevelItem(0).text(0) == "Evidence verified"

    first = window.batch_results.topLevelItem(0)
    window._open_batch_result(first, 0)
    assert window.job_heading.text() == "Example 1 — Systems Engineer 1"
    window.close()


def test_window_labels_location_conditions_without_saying_meet_every_item() -> None:
    _application()
    fixture = load_review_fixtures()[1]
    requirement = fixture.groups[0].paths[0].requirements[0]
    conditional = QualificationGroupReview(
        label="Conditional Location Requirements",
        priority=RequirementPriority.REQUIRED,
        paths=(
            QualificationPathReview(
                label="Location Applicability Path",
                requirements=(requirement,),
            ),
        ),
    )
    result = replace(fixture, groups=(conditional,))

    window = QualificationReviewWindow((result,))
    window.fixture_picker.setCurrentIndex(1)
    QApplication.processEvents()

    group_item = window.qualification_tree.topLevelItem(0)
    assert "conditional" in group_item.text(0).casefold()
    assert "location" in group_item.text(0).casefold()
    assert "only items matching" in group_item.child(0).text(0).casefold()
    assert "meet every item" not in group_item.child(0).text(0).casefold()
    window.close()


def test_window_runs_non_authoritative_shadow_match() -> None:
    _application()
    job = load_review_fixtures()[1]
    resume = replace(
        job,
        company="Resume",
        title="resume.docx",
        document_kind="resume",
    )
    window = QualificationReviewWindow((job,))

    window._load_fixture(resume)
    assert not window.shadow_match_button.isEnabled()
    assert window.interpret_button.text() == "Interpret resume"
    window._load_fixture(job)
    assert window.shadow_match_button.isEnabled()
    assert window.interpret_button.text() == "Interpret posting"

    window.shadow_match_button.click()

    assert not window.shadow_match_tree.isHidden()
    assert window.shadow_match_tree.topLevelItemCount() > 0
    assert "no recommendation or omission" in window.engine_message.text().casefold()
    window.close()


def test_shadow_match_control_remains_visible_in_engine_panel() -> None:
    _application()
    fixture = load_review_fixtures()[1]
    window = QualificationReviewWindow((fixture,))
    window.resize(1280, 800)
    window.show()
    QApplication.processEvents()

    assert window.shadow_match_button.isVisible()
    assert window.shadow_match_button.height() > 0
    assert window.result_splitter.orientation() is Qt.Orientation.Vertical
    window.close()
