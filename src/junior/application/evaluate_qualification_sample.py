"""Run a copied evaluation sample through the existing interpretation path."""

from collections.abc import Callable
from dataclasses import dataclass
from time import monotonic

from junior.application.evaluation_sample import EvaluationPosting
from junior.application.interpret_qualification_review import (
    QualificationInterpretationError,
)
from junior.application.review_workspace import ReviewWorkspaceResult
from junior.infrastructure.ollama_qualification_backend import (
    LocalModelUnavailableError,
)

InterpretationRunner = Callable[
    [str, str, str, str, str | None], ReviewWorkspaceResult
]


@dataclass(frozen=True, slots=True)
class QualificationSampleOutcome:
    posting: EvaluationPosting
    elapsed_seconds: float
    result: ReviewWorkspaceResult | None = None
    failure_message: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.result is not None


@dataclass(slots=True)
class EvaluateQualificationSample:
    runner: InterpretationRunner
    clock: Callable[[], float] = monotonic

    def execute(
        self,
        *,
        postings: tuple[EvaluationPosting, ...],
        model_name: str,
        on_completed: Callable[[QualificationSampleOutcome, int, int], None],
        should_stop: Callable[[], bool],
    ) -> tuple[QualificationSampleOutcome, ...]:
        """Interpret sequentially, retaining each completed success or failure."""

        outcomes: list[QualificationSampleOutcome] = []
        total = len(postings)
        for index, posting in enumerate(postings, start=1):
            if should_stop():
                break
            started = self.clock()
            try:
                result = self.runner(
                    model_name,
                    posting.title,
                    posting.company,
                    posting.description,
                    posting.source_url,
                )
                outcome = QualificationSampleOutcome(
                    posting=posting,
                    elapsed_seconds=max(0.0, self.clock() - started),
                    result=result,
                )
            except (
                QualificationInterpretationError,
                LocalModelUnavailableError,
            ) as exc:
                outcome = QualificationSampleOutcome(
                    posting=posting,
                    elapsed_seconds=max(0.0, self.clock() - started),
                    failure_message=str(exc),
                )
            except Exception:
                outcome = QualificationSampleOutcome(
                    posting=posting,
                    elapsed_seconds=max(0.0, self.clock() - started),
                    failure_message=(
                        "Junior encountered an unexpected local interpretation "
                        "problem. No model claims were accepted."
                    ),
                )
            outcomes.append(outcome)
            on_completed(outcome, index, total)
        return tuple(outcomes)
