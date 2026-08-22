"""Native qualification-review workspace; presentation only."""

import zipfile
from collections.abc import Callable
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Qt, QThread, Signal, Slot
from PySide6.QtGui import QCloseEvent, QColor, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMenu,
    QPushButton,
    QSplitter,
    QTextEdit,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from junior.application.evaluate_qualification_sample import (
    EvaluateQualificationSample,
    QualificationSampleOutcome,
)
from junior.application.evaluation_sample import EvaluationPosting
from junior.application.interpret_qualification_review import (
    QualificationInterpretationError,
)
from junior.application.review_workspace import (
    RequirementReview,
    ReviewValidationState,
    ReviewWorkspaceResult,
)
from junior.infrastructure.ollama_qualification_backend import (
    LocalModelUnavailableError,
)
from junior.infrastructure.rc6_raw_scan_importer import (
    RawScanImportError,
    import_rc6_evaluation_sample,
)
from junior.infrastructure.resume_file_importer import (
    ResumeImportError,
    import_resume_text,
)
from junior.scoring.qualification_shadow_matcher import (
    ShadowMatchState,
    match_review_results,
)

_EVIDENCE_ROLE = Qt.ItemDataRole.UserRole
InterpretationRunner = Callable[
    [str, str, str, str, str | None], ReviewWorkspaceResult
]
ResumeInterpretationRunner = Callable[[str, str, str], ReviewWorkspaceResult]


class _InterpretationWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        runner: InterpretationRunner,
        model_name: str,
        title: str,
        company: str,
        content: str,
        source_uri: str | None,
    ) -> None:
        super().__init__()
        self._runner = runner
        self._arguments = (model_name, title, company, content, source_uri)

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self._runner(*self._arguments))
        except (QualificationInterpretationError, LocalModelUnavailableError) as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit(
                "Junior encountered an unexpected local interpretation problem. "
                "No model claims were accepted and the scoring engine was not run."
            )
        finally:
            self.finished.emit()


class _ResumeInterpretationWorker(QObject):
    succeeded = Signal(object)
    failed = Signal(str)
    finished = Signal()

    def __init__(
        self,
        runner: ResumeInterpretationRunner,
        model_name: str,
        filename: str,
        content: str,
    ) -> None:
        super().__init__()
        self._runner = runner
        self._arguments = (model_name, filename, content)

    @Slot()
    def run(self) -> None:
        try:
            self.succeeded.emit(self._runner(*self._arguments))
        except (LocalModelUnavailableError, ValueError) as exc:
            self.failed.emit(str(exc))
        except Exception:
            self.failed.emit(
                "Junior encountered an unexpected resume interpretation problem. "
                "No model claims were accepted and the scoring engine was not run."
            )
        finally:
            self.finished.emit()


class _BatchEvaluationWorker(QObject):
    progressed = Signal(object, int, int)
    finished = Signal(bool)

    def __init__(
        self,
        runner: InterpretationRunner,
        model_name: str,
        postings: tuple[EvaluationPosting, ...],
    ) -> None:
        super().__init__()
        self._service = EvaluateQualificationSample(runner)
        self._model_name = model_name
        self._postings = postings
        self._stop_requested = Event()

    def request_stop(self) -> None:
        self._stop_requested.set()

    @Slot()
    def run(self) -> None:
        self._service.execute(
            postings=self._postings,
            model_name=self._model_name,
            on_completed=self.progressed.emit,
            should_stop=self._stop_requested.is_set,
        )
        self.finished.emit(self._stop_requested.is_set())


class QualificationReviewWindow(QMainWindow):
    def __init__(
        self,
        fixtures: tuple[ReviewWorkspaceResult, ...],
        interpretation_runner: InterpretationRunner | None = None,
        resume_interpretation_runner: ResumeInterpretationRunner | None = None,
    ) -> None:
        super().__init__()
        if not fixtures:
            raise ValueError("the review workspace requires at least one result")
        self._fixtures = {fixture.fixture_id: fixture for fixture in fixtures}
        self._imported_postings: dict[str, EvaluationPosting] = {}
        self._current_source_uri: str | None = None
        self._interpretation_runner = interpretation_runner
        self._resume_interpretation_runner = resume_interpretation_runner
        self._input_kind = "job"
        self._resume_filename = "Resume"
        self._worker_thread: QThread | None = None
        self._worker: (
            _InterpretationWorker
            | _ResumeInterpretationWorker
            | _BatchEvaluationWorker
            | None
        ) = None
        self._batch_outcomes: dict[str, QualificationSampleOutcome] = {}
        self._latest_job_result: ReviewWorkspaceResult | None = None
        self._latest_resume_result: ReviewWorkspaceResult | None = None
        self._current_result: ReviewWorkspaceResult | None = None
        self.setWindowTitle("Junior 2.0 — Qualification Review")
        self.resize(1280, 800)
        self.setMinimumSize(900, 620)
        self._build_menu()
        self._build_workspace(fixtures)
        self._show_interactive_workspace()

    def _build_menu(self) -> None:
        file_menu = QMenu("&File", self)
        exit_action = file_menu.addAction("E&xit")
        exit_action.setShortcut("Ctrl+Q")
        exit_action.triggered.connect(self.close)
        self.menuBar().addMenu(file_menu)

    def _build_workspace(
        self,
        fixtures: tuple[ReviewWorkspaceResult, ...],
    ) -> None:
        central = QWidget()
        outer = QVBoxLayout(central)
        outer.setContentsMargins(20, 16, 20, 20)
        outer.setSpacing(12)

        title = QLabel("Qualification Review")
        title.setObjectName("pageTitle")
        title.setAccessibleName("Qualification Review")
        outer.addWidget(title)

        preview = QLabel(
            "Interpretation experiment — paste a real posting or inspect a reviewed "
            "example. Shadow matching is available; recommendations remain disabled."
        )
        preview.setWordWrap(True)
        preview.setObjectName("previewBanner")
        outer.addWidget(preview)

        chooser_row = QHBoxLayout()
        chooser_label = QLabel("Input:")
        self.fixture_picker = QComboBox()
        self.fixture_picker.setAccessibleName("Interpretation input")
        self.fixture_picker.addItem("Paste a real job posting", "interactive")
        for fixture in fixtures:
            self.fixture_picker.addItem(
                f"{fixture.company} — {fixture.title}",
                fixture.fixture_id,
            )
        self.fixture_picker.currentIndexChanged.connect(self._fixture_changed)
        self.import_button = QPushButton("Import RC6 raw scan")
        self.import_button.clicked.connect(self._import_rc6_sample)
        self.batch_button = QPushButton("Run evaluation sample")
        self.batch_button.setEnabled(False)
        self.batch_button.clicked.connect(self._start_batch_evaluation)
        self.resume_button = QPushButton("Import resume")
        self.resume_button.clicked.connect(self._import_resume)
        self.stop_batch_button = QPushButton("Stop after current posting")
        self.stop_batch_button.clicked.connect(self._stop_batch_evaluation)
        self.stop_batch_button.hide()
        chooser_row.addWidget(chooser_label)
        chooser_row.addWidget(self.fixture_picker, 1)
        chooser_row.addWidget(self.import_button)
        chooser_row.addWidget(self.resume_button)
        chooser_row.addWidget(self.batch_button)
        chooser_row.addWidget(self.stop_batch_button)
        outer.addLayout(chooser_row)

        self.interactive_controls = QWidget()
        interactive_layout = QHBoxLayout(self.interactive_controls)
        interactive_layout.setContentsMargins(0, 0, 0, 0)
        self.company_input = QLineEdit()
        self.company_input.setPlaceholderText("Company (optional)")
        self.company_input.setAccessibleName("Company")
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Job title (optional)")
        self.title_input.setAccessibleName("Job title")
        self.model_input = QLineEdit("qwen2.5:3b")
        self.model_input.setAccessibleName("Ollama model name")
        self.interpret_button = QPushButton("Interpret posting")
        self.interpret_button.clicked.connect(self._start_interpretation)
        interactive_layout.addWidget(self.company_input)
        interactive_layout.addWidget(self.title_input)
        interactive_layout.addWidget(self.model_input)
        interactive_layout.addWidget(self.interpret_button)
        outer.addWidget(self.interactive_controls)

        self.interpretation_status = QLabel(
            "Paste a complete job posting below, then run the local model. "
            "This does not score the job."
        )
        self.interpretation_status.setWordWrap(True)
        self.interpretation_status.setObjectName("interpretationStatus")
        outer.addWidget(self.interpretation_status)

        self.batch_box = QGroupBox("Evaluation sample progress")
        batch_layout = QVBoxLayout(self.batch_box)
        self.batch_status = QLabel()
        self.batch_status.setWordWrap(True)
        self.batch_results = QTreeWidget()
        self.batch_results.setHeaderLabels(
            [
                "Status",
                "Company",
                "Job title",
                "Requirements",
                "Conditional",
                "Time",
            ]
        )
        self.batch_results.setAccessibleName("Evaluation sample results")
        self.batch_results.setAlternatingRowColors(True)
        self.batch_results.setMaximumHeight(260)
        self.batch_results.itemActivated.connect(self._open_batch_result)
        batch_layout.addWidget(self.batch_status)
        batch_layout.addWidget(self.batch_results)
        self.batch_box.hide()
        outer.addWidget(self.batch_box)

        self.job_heading = QLabel()
        self.job_heading.setObjectName("jobHeading")
        outer.addWidget(self.job_heading)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._build_source_panel())
        splitter.addWidget(self._build_results_panel())
        splitter.setSizes([540, 700])
        outer.addWidget(splitter, 1)

        self.setCentralWidget(central)
        self.setStyleSheet(_STYLE_SHEET)

    def _build_source_panel(self) -> QWidget:
        self.source_box = QGroupBox("Original job posting")
        layout = QVBoxLayout(self.source_box)
        self.source_hint = QLabel(
            "Select a qualification to highlight its exact source text."
        )
        self.source_hint.setWordWrap(True)
        self.source_text = QTextEdit()
        self.source_text.setReadOnly(True)
        self.source_text.setAccessibleName("Original job posting")
        self.source_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        layout.addWidget(self.source_hint)
        layout.addWidget(self.source_text, 1)
        return self.source_box

    def _build_results_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)

        self.validation_card = QFrame()
        validation_layout = QVBoxLayout(self.validation_card)
        self.validation_heading = QLabel()
        self.validation_heading.setObjectName("validationHeading")
        self.validation_message = QLabel()
        self.validation_message.setWordWrap(True)
        validation_layout.addWidget(self.validation_heading)
        validation_layout.addWidget(self.validation_message)
        layout.addWidget(self.validation_card)

        qualification_box = QGroupBox("What Junior found")
        qualification_layout = QVBoxLayout(qualification_box)
        self.qualification_tree = QTreeWidget()
        self.qualification_tree.setHeaderLabels(
            ["Qualification", "Type", "Evidence status"]
        )
        self.qualification_tree.setAccessibleName("Extracted qualifications")
        self.qualification_tree.setAlternatingRowColors(True)
        self.qualification_tree.setRootIsDecorated(True)
        self.qualification_tree.itemSelectionChanged.connect(
            self._highlight_selected_evidence
        )
        qualification_layout.addWidget(self.qualification_tree)
        self.qualification_box = qualification_box

        self.rejected_box = QGroupBox("Rejected model claims")
        rejected_layout = QVBoxLayout(self.rejected_box)
        self.rejected_list = QListWidget()
        self.rejected_list.setAccessibleName("Rejected model claims")
        rejected_layout.addWidget(self.rejected_list)
        layout.addWidget(self.rejected_box)

        engine_box = QGroupBox("Deterministic engine result")
        engine_box.setMinimumHeight(105)
        engine_layout = QVBoxLayout(engine_box)
        self.engine_message = QLabel()
        self.engine_message.setWordWrap(True)
        engine_layout.addWidget(self.engine_message)
        self.shadow_match_button = QPushButton("Run shadow match")
        self.shadow_match_button.setEnabled(False)
        self.shadow_match_button.clicked.connect(self._run_shadow_match)
        engine_layout.addWidget(self.shadow_match_button)
        self.shadow_match_tree = QTreeWidget()
        self.shadow_match_tree.setHeaderLabels(
            [
                "Job requirement",
                "Requirement path",
                "Priority",
                "Shadow result",
                "Resume evidence",
                "Reason",
            ]
        )
        self.shadow_match_tree.setAlternatingRowColors(True)
        self.shadow_match_tree.hide()
        engine_layout.addWidget(self.shadow_match_tree)
        self.engine_box = engine_box
        self.result_splitter = QSplitter(Qt.Orientation.Vertical)
        self.result_splitter.setChildrenCollapsible(False)
        self.result_splitter.addWidget(self.qualification_box)
        self.result_splitter.addWidget(self.engine_box)
        self.result_splitter.setStretchFactor(0, 1)
        self.result_splitter.setStretchFactor(1, 2)
        self.result_splitter.setSizes([260, 360])
        layout.addWidget(self.result_splitter, 1)

        self.details_button = QToolButton()
        self.details_button.setText("Technical details")
        self.details_button.setCheckable(True)
        self.details_button.setArrowType(Qt.ArrowType.RightArrow)
        self.details_button.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )
        self.details_button.setAccessibleName("Show technical details")
        self.details_button.toggled.connect(self._toggle_technical_details)
        layout.addWidget(self.details_button)

        self.technical_details = QTextEdit()
        self.technical_details.setReadOnly(True)
        self.technical_details.setAccessibleName("Technical details")
        self.technical_details.setMaximumHeight(150)
        self.technical_details.hide()
        layout.addWidget(self.technical_details)
        return panel

    def _fixture_changed(self, index: int) -> None:
        fixture_id = self.fixture_picker.itemData(index)
        if fixture_id == "interactive":
            self._show_interactive_workspace()
            return
        if fixture_id in self._imported_postings:
            self._show_imported_posting(self._imported_postings[fixture_id])
            return
        if fixture_id in self._fixtures:
            self._load_fixture(self._fixtures[fixture_id])

    def _show_interactive_workspace(self) -> None:
        self._current_result = None
        self._input_kind = "job"
        self._current_source_uri = None
        self.interactive_controls.show()
        self.interpretation_status.show()
        self.job_heading.setText("Local qualification interpretation")
        self.source_box.setTitle("Original job posting")
        self.interpret_button.setText("Interpret posting")
        self.source_text.setReadOnly(False)
        self.source_text.setPlaceholderText("Paste the complete job posting here")
        self.source_text.clear()
        self.qualification_tree.clear()
        self.validation_heading.setText("Waiting for a posting")
        self.validation_message.setText(
            "Junior will show only qualifications that pass its contract and "
            "exact-evidence check."
        )
        self.validation_card.setProperty("validationState", "needs_review")
        self.engine_message.setText(
            "Not connected. This experiment cannot recommend or omit the job."
        )
        self.shadow_match_button.setEnabled(False)
        self.shadow_match_tree.hide()
        self.rejected_box.hide()
        self.technical_details.clear()

    def _show_imported_posting(self, posting: EvaluationPosting) -> None:
        self._input_kind = "job"
        self._current_source_uri = posting.source_url
        self.interactive_controls.show()
        self.interpretation_status.show()
        self.company_input.setText(posting.company)
        self.title_input.setText(posting.title)
        self.job_heading.setText(f"{posting.company} — {posting.title}")
        self.source_text.setReadOnly(False)
        self.source_text.setPlainText(posting.description)
        self.qualification_tree.clear()
        self.validation_heading.setText("Ready for interpretation")
        self.validation_message.setText(
            f"RC6 sample category: {posting.sample_category}."
        )
        self.validation_card.setProperty("validationState", "needs_review")
        self.engine_message.setText(
            "Not connected. This evaluation cannot recommend or omit the job."
        )
        self.rejected_box.hide()
        self.technical_details.setPlainText(f"Source URL: {posting.source_url}")
        self.interpretation_status.setText(
            "Imported from a copied RC6 raw-scan export. Select Interpret posting."
        )

    def _import_resume(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose a resume",
            "",
            "Resume files (*.pdf *.docx *.txt)",
        )
        if not path:
            return
        try:
            content = import_resume_text(path)
        except ResumeImportError as exc:
            self.interpretation_status.setText(str(exc))
            return
        self._input_kind = "resume"
        self._resume_filename = Path(path).name
        self.fixture_picker.setCurrentIndex(0)
        self.interactive_controls.show()
        self.interpretation_status.show()
        self.company_input.clear()
        self.title_input.setText(self._resume_filename)
        self.job_heading.setText(f"Resume — {self._resume_filename}")
        self.source_box.setTitle("Original resume")
        self.source_text.setReadOnly(False)
        self.source_text.setPlainText(content)
        self.interpret_button.setText("Interpret resume")
        self.qualification_tree.clear()
        self.validation_heading.setText("Ready for resume interpretation")
        self.validation_message.setText(
            "The complete resume stays local; only exact-evidence qualifications "
            "will be displayed."
        )
        self.engine_message.setText(
            "Not connected. Junior will not match or score this resume."
        )
        self.interpretation_status.setText(
            "Resume imported locally. Select Interpret resume to inspect extraction."
        )

    def _import_rc6_sample(self) -> None:
        path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            "Choose an RC6 raw-scan export",
            "",
            "Junior raw-scan ZIP (*.zip)",
        )
        if not path:
            return
        try:
            sample = import_rc6_evaluation_sample(path)
        except (
            RawScanImportError,
            OSError,
            UnicodeError,
            ValueError,
            zipfile.BadZipFile,
        ):
            self.interpretation_status.setText(
                "Junior could not read that file as an RC6 raw-scan export. "
                "Download the raw scan from RC6 Reports and try again."
            )
            return
        self._remove_imported_picker_items()
        self._imported_postings = {
            f"rc6:{posting.posting_id}": posting for posting in sample.postings
        }
        self._batch_outcomes.clear()
        self.batch_results.clear()
        self.batch_box.show()
        self.batch_status.setText(
            "Ready to evaluate the imported sample. Completed results remain "
            "available here until Junior closes or another sample is imported."
        )
        self.batch_button.setEnabled(bool(self._imported_postings))
        for item_id, posting in self._imported_postings.items():
            self.fixture_picker.addItem(
                f"RC6 · {posting.company} — {posting.title}", item_id
            )
        self.interpretation_status.setText(
            f"Imported {len(sample.postings)} evaluation postings from "
            f"{sample.jobs_in_export} collected jobs ({sample.source_build})."
        )
        if self._imported_postings:
            first_id = next(iter(self._imported_postings))
            self.fixture_picker.setCurrentIndex(self.fixture_picker.findData(first_id))

    def _remove_imported_picker_items(self) -> None:
        for index in range(self.fixture_picker.count() - 1, -1, -1):
            if str(self.fixture_picker.itemData(index)).startswith("rc6:"):
                self.fixture_picker.removeItem(index)

    def _start_interpretation(self) -> None:
        content = self.source_text.toPlainText().strip()
        model_name = self.model_input.text().strip()
        if not content:
            message = (
                "Import a complete resume before running interpretation."
                if self._input_kind == "resume"
                else "Paste a complete job posting before running interpretation."
            )
            self.interpretation_status.setText(message)
            return
        if not model_name:
            self.interpretation_status.setText("Enter an installed Ollama model name.")
            return
        runner_available = (
            self._resume_interpretation_runner
            if self._input_kind == "resume"
            else self._interpretation_runner
        )
        if runner_available is None:
            self.interpretation_status.setText(
                "The local-model adapter is not available in this build."
            )
            return
        self.interpret_button.setEnabled(False)
        subject = "resume" if self._input_kind == "resume" else "posting"
        self.interpretation_status.setText(
            f"The local model is reading the {subject}. Junior will verify its output."
        )
        thread = QThread(self)
        if self._input_kind == "resume":
            worker = _ResumeInterpretationWorker(
                self._resume_interpretation_runner,
                model_name,
                self._resume_filename,
                content,
            )
        else:
            worker = _InterpretationWorker(
                self._interpretation_runner,
                model_name,
                self.title_input.text(),
                self.company_input.text(),
                content,
                self._current_source_uri,
            )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.succeeded.connect(self._interpretation_succeeded)
        worker.failed.connect(self._interpretation_failed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._interpretation_finished)
        self._worker_thread = thread
        self._worker = worker
        thread.start()

    def _start_batch_evaluation(self) -> None:
        if self._worker_thread is not None:
            return
        model_name = self.model_input.text().strip()
        if not model_name:
            self.batch_status.setText("Enter an installed Ollama model name.")
            return
        if self._interpretation_runner is None:
            self.batch_status.setText(
                "The local-model adapter is not available in this build."
            )
            return
        postings = tuple(self._imported_postings.values())
        if not postings:
            self.batch_status.setText("Import an RC6 evaluation sample first.")
            return

        self._batch_outcomes.clear()
        self.batch_results.clear()
        self.batch_box.show()
        self.batch_status.setText(
            f"Starting 0 of {len(postings)}. You may use other applications while "
            "Junior works in the background."
        )
        self._set_run_controls_enabled(False)
        self.stop_batch_button.show()
        thread = QThread(self)
        worker = _BatchEvaluationWorker(
            self._interpretation_runner, model_name, postings
        )
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.progressed.connect(self._batch_progressed)
        worker.finished.connect(thread.quit)
        worker.finished.connect(self._batch_completed)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.finished.connect(self._batch_thread_finished)
        self._worker_thread = thread
        self._worker = worker
        thread.start()

    def _stop_batch_evaluation(self) -> None:
        if isinstance(self._worker, _BatchEvaluationWorker):
            self._worker.request_stop()
            self.stop_batch_button.setEnabled(False)
            self.batch_status.setText(
                "Stop requested. Junior will stop after the current posting finishes."
            )

    @Slot(object, int, int)
    def _batch_progressed(
        self, outcome: QualificationSampleOutcome, index: int, total: int
    ) -> None:
        self._batch_outcomes[outcome.posting.posting_id] = outcome
        if outcome.result is None:
            status = "Failed"
            requirements = "—"
            conditional = "—"
        else:
            status = "Evidence verified"
            requirements = str(
                sum(
                    len(path.requirements)
                    for group in outcome.result.groups
                    for path in group.paths
                )
            )
            conditional = str(
                sum(
                    len(path.requirements)
                    for group in outcome.result.groups
                    if group.label == "Conditional Location Requirements"
                    for path in group.paths
                )
            )
        item = QTreeWidgetItem(
            [
                status,
                outcome.posting.company,
                outcome.posting.title,
                requirements,
                conditional,
                f"{outcome.elapsed_seconds:.1f}s",
            ]
        )
        item.setData(0, Qt.ItemDataRole.UserRole, outcome.posting.posting_id)
        if outcome.failure_message:
            item.setToolTip(0, outcome.failure_message)
        self.batch_results.addTopLevelItem(item)
        self.batch_status.setText(
            f"Completed {index} of {total}: {outcome.posting.company} — "
            f"{outcome.posting.title}. Activate a successful row to inspect it."
        )

    @Slot(bool)
    def _batch_completed(self, stopped: bool) -> None:
        completed = len(self._batch_outcomes)
        succeeded = sum(item.succeeded for item in self._batch_outcomes.values())
        failed = completed - succeeded
        state = "Stopped" if stopped else "Finished"
        self.batch_status.setText(
            f"{state}: {completed} processed, {succeeded} evidence verified, "
            f"{failed} failed. "
            "Activate a successful row to inspect its evidence."
        )
        self.stop_batch_button.hide()
        self.stop_batch_button.setEnabled(True)
        self._set_run_controls_enabled(True)

    @Slot()
    def _batch_thread_finished(self) -> None:
        self._worker_thread = None
        self._worker = None

    @Slot(QTreeWidgetItem, int)
    def _open_batch_result(self, item: QTreeWidgetItem, _column: int) -> None:
        posting_id = item.data(0, Qt.ItemDataRole.UserRole)
        outcome = self._batch_outcomes.get(str(posting_id))
        if outcome is None:
            return
        if outcome.result is not None:
            self._load_fixture(outcome.result)
            self.batch_box.show()
            return
        self.interpretation_status.setText(
            outcome.failure_message or "This posting could not be interpreted."
        )

    def _set_run_controls_enabled(self, enabled: bool) -> None:
        self.import_button.setEnabled(enabled)
        self.resume_button.setEnabled(enabled)
        self.fixture_picker.setEnabled(enabled)
        self.interpret_button.setEnabled(enabled)
        self.batch_button.setEnabled(enabled and bool(self._imported_postings))

    @Slot(object)
    def _interpretation_succeeded(self, result: ReviewWorkspaceResult) -> None:
        self._load_fixture(result)
        self.source_text.setReadOnly(False)
        self.interactive_controls.show()
        self.interpretation_status.show()
        self.interpretation_status.setText(
            "Interpretation completed and exact source evidence was verified."
        )

    @Slot(str)
    def _interpretation_failed(self, message: str) -> None:
        self.interpretation_status.setText(message)
        self.validation_heading.setText("Interpretation not accepted")
        self.validation_message.setText(
            "No model claims were added to this review. The scoring engine was not run."
        )
        self.validation_card.setProperty("validationState", "rejected")

    @Slot()
    def _interpretation_finished(self) -> None:
        self.interpret_button.setEnabled(True)
        self._worker_thread = None
        self._worker = None

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._worker_thread is not None and self._worker_thread.isRunning():
            self.interpretation_status.setText(
                "Wait for the local model request to finish before closing Junior."
            )
            event.ignore()
            return
        super().closeEvent(event)

    def _load_fixture(self, result: ReviewWorkspaceResult) -> None:
        self._current_result = result
        self._input_kind = result.document_kind
        self.interpret_button.setText(
            "Interpret resume"
            if result.document_kind == "resume"
            else "Interpret posting"
        )
        if (
            result.validation_state is ReviewValidationState.VALIDATED
            and result.document_kind == "resume"
        ):
            self._latest_resume_result = result
        elif (
            result.validation_state is ReviewValidationState.VALIDATED
            and result.document_kind == "job"
        ):
            self._latest_job_result = result
        is_interactive = result.fixture_id.startswith("interactive-")
        self.interactive_controls.setVisible(is_interactive)
        self.interpretation_status.setVisible(is_interactive)
        self.job_heading.setText(f"{result.company} — {result.title}")
        self.source_box.setTitle(
            "Original resume"
            if result.document_kind == "resume"
            else "Original job posting"
        )
        self.source_text.setPlainText(result.source_document.content)
        self.source_text.setReadOnly(not is_interactive)
        self._clear_evidence_highlight()
        self._populate_qualification_tree(result)
        self._set_validation_state(result)
        self.engine_message.setText(result.engine_message)
        self.shadow_match_tree.hide()
        self.shadow_match_button.setEnabled(
            result.document_kind == "job"
            and self._latest_job_result is not None
            and self._latest_resume_result is not None
        )
        self.rejected_list.clear()
        self.rejected_list.addItems(result.rejected_claims)
        self.rejected_box.setVisible(bool(result.rejected_claims))
        details = "\n".join(
            f"{label}: {value}" for label, value in result.technical_details
        )
        self.technical_details.setPlainText(details)
        status = (
            "Local model interpretation loaded"
            if is_interactive
            else "Reviewed example loaded"
        )
        self.statusBar().showMessage(status)

    def _run_shadow_match(self) -> None:
        if (
            self._current_result is None
            or self._current_result.document_kind != "job"
            or self._latest_resume_result is None
        ):
            return
        result = match_review_results(
            self._current_result, self._latest_resume_result
        )
        self.shadow_match_tree.clear()
        labels = {
            ShadowMatchState.EVIDENCED: "Evidence found",
            ShadowMatchState.NOT_FOUND: "Not found",
            ShadowMatchState.NEEDS_REVIEW: "Needs review",
        }
        for match in result.matches:
            resume_evidence = "; ".join(
                item.label for item in match.resume_evidence
            )
            item = QTreeWidgetItem(
                [
                    match.requirement.label,
                    f"{match.group_label} / {match.path_label}",
                    match.priority.title(),
                    labels[match.state],
                    resume_evidence,
                    match.reason,
                ]
            )
            item.setToolTip(3, match.reason)
            self.shadow_match_tree.addTopLevelItem(item)
        evidenced = result.count(ShadowMatchState.EVIDENCED)
        not_found = result.count(ShadowMatchState.NOT_FOUND)
        needs_review = result.count(ShadowMatchState.NEEDS_REVIEW)
        self.engine_message.setText(
            "Shadow comparison only — no recommendation or omission was made. "
            f"{evidenced} evidenced, {not_found} not found, "
            f"{needs_review} need review."
        )
        self.shadow_match_tree.show()
        available_height = max(self.result_splitter.height(), 500)
        self.result_splitter.setSizes(
            [available_height // 3, available_height * 2 // 3]
        )
        for column in range(6):
            self.shadow_match_tree.resizeColumnToContents(column)

    def _populate_qualification_tree(self, result: ReviewWorkspaceResult) -> None:
        self.qualification_tree.clear()
        if not result.groups:
            empty = QTreeWidgetItem(
                ["No qualification section was stated", "", "Nothing invented"]
            )
            self.qualification_tree.addTopLevelItem(empty)
            return
        for group in result.groups:
            if result.document_kind == "resume":
                group_item = QTreeWidgetItem(["Resume qualifications", "", ""])
                group_item.setExpanded(True)
                self.qualification_tree.addTopLevelItem(group_item)
                for path in group.paths:
                    for requirement in path.requirements:
                        group_item.addChild(
                            self._requirement_item(requirement, result)
                        )
                continue
            priority = group.priority.value.title()
            is_location_conditional = (
                group.label == "Conditional Location Requirements"
            )
            choice_text = (
                " — meet any one option" if len(group.paths) > 1 else ""
            )
            group_label = (
                "Conditional: location-specific requirements"
                if is_location_conditional
                else f"{priority}: {group.label}{choice_text}"
            )
            group_item = QTreeWidgetItem(
                [group_label, "", ""]
            )
            group_item.setExpanded(True)
            self.qualification_tree.addTopLevelItem(group_item)
            for index, path in enumerate(group.paths, start=1):
                if is_location_conditional:
                    path_label = "Only items matching the job location apply"
                else:
                    path_label = (
                        f"Option {index} — meet every item"
                        if len(group.paths) > 1
                        else "Meet every item"
                    )
                path_item = QTreeWidgetItem([path_label, "", ""])
                path_item.setExpanded(True)
                group_item.addChild(path_item)
                for requirement in path.requirements:
                    path_item.addChild(self._requirement_item(requirement, result))
        self.qualification_tree.resizeColumnToContents(0)
        self.qualification_tree.resizeColumnToContents(1)

    def _requirement_item(
        self,
        requirement: RequirementReview,
        result: ReviewWorkspaceResult,
    ) -> QTreeWidgetItem:
        evidence_status = (
            "Rejected"
            if result.validation_state is ReviewValidationState.REJECTED
            else "Exact quote verified"
        )
        item = QTreeWidgetItem(
            [requirement.label, requirement.category, evidence_status]
        )
        if requirement.evidence:
            evidence = requirement.evidence[0]
            item.setData(
                0,
                _EVIDENCE_ROLE,
                (evidence.start, evidence.end, evidence.quote),
            )
        return item

    def _set_validation_state(self, result: ReviewWorkspaceResult) -> None:
        labels = {
            ReviewValidationState.VALIDATED: "Evidence validated",
            ReviewValidationState.NEEDS_REVIEW: "Needs review",
            ReviewValidationState.REJECTED: "Model claim rejected",
        }
        self.validation_heading.setText(labels[result.validation_state])
        self.validation_message.setText(result.validation_message)
        self.validation_card.setProperty(
            "validationState", result.validation_state.value
        )
        self.validation_card.style().unpolish(self.validation_card)
        self.validation_card.style().polish(self.validation_card)

    def _highlight_selected_evidence(self) -> None:
        selected = self.qualification_tree.selectedItems()
        if not selected:
            self._clear_evidence_highlight()
            return
        evidence = selected[0].data(0, _EVIDENCE_ROLE)
        if not evidence:
            self._clear_evidence_highlight()
            return
        start, end, _quote = evidence
        cursor = self.source_text.textCursor()
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
        selection = QTextEdit.ExtraSelection()
        selection.cursor = cursor
        selection.format = QTextCharFormat()
        selection.format.setBackground(QColor("#fff1a8"))
        selection.format.setForeground(QColor("#111111"))
        self.source_text.setExtraSelections([selection])
        self.source_text.setTextCursor(cursor)
        self.source_text.ensureCursorVisible()

    def _clear_evidence_highlight(self) -> None:
        self.source_text.setExtraSelections([])

    def _toggle_technical_details(self, checked: bool) -> None:
        self.technical_details.setVisible(checked)
        self.details_button.setArrowType(
            Qt.ArrowType.DownArrow if checked else Qt.ArrowType.RightArrow
        )
        self.details_button.setAccessibleName(
            "Hide technical details" if checked else "Show technical details"
        )


_STYLE_SHEET = """
QMainWindow, QWidget {
    background: #15171b;
    color: #f2f4f7;
    font-size: 14px;
}
QLabel#pageTitle {
    font-size: 26px;
    font-weight: 700;
}
QLabel#jobHeading {
    font-size: 18px;
    font-weight: 650;
}
QLabel#previewBanner {
    background: #25354a;
    border: 1px solid #4f759f;
    border-radius: 6px;
    padding: 10px;
}
QGroupBox {
    border: 1px solid #3c414a;
    border-radius: 7px;
    margin-top: 12px;
    padding-top: 10px;
    font-weight: 650;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
}
QTextEdit, QTreeWidget, QListWidget, QComboBox, QLineEdit {
    background: #202329;
    color: #f2f4f7;
    border: 1px solid #474d57;
    border-radius: 4px;
    selection-background-color: #176fa6;
}
QTreeWidget::item { padding: 5px; }
QFrame[validationState="validated"] {
    background: #173b2d;
    border: 1px solid #3b9b72;
    border-radius: 6px;
}
QFrame[validationState="needs_review"] {
    background: #473b1b;
    border: 1px solid #c5a342;
    border-radius: 6px;
}
QFrame[validationState="rejected"] {
    background: #4a2329;
    border: 1px solid #cf6673;
    border-radius: 6px;
}
QToolButton, QPushButton {
    color: #6cc7ff;
    background: transparent;
    border: none;
    padding: 5px;
}
"""
