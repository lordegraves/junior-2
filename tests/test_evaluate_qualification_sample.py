from dataclasses import replace

from junior.application.evaluate_qualification_sample import (
    EvaluateQualificationSample,
)
from junior.application.evaluation_sample import EvaluationPosting
from junior.application.interpret_qualification_review import (
    QualificationFailureCode,
    QualificationInterpretationError,
)
from junior.application.review_fixtures import load_review_fixtures


def _posting(number: int) -> EvaluationPosting:
    return EvaluationPosting(
        posting_id=f"posting-{number}",
        company=f"Company {number}",
        title=f"Role {number}",
        description=f"Complete public posting {number}",
        source_url=f"https://example.invalid/jobs/{number}",
        sample_category="general",
    )


def test_batch_continues_after_safe_interpretation_failure() -> None:
    fixture = load_review_fixtures()[1]
    completed = []

    def runner(_model, title, company, _content, _source_url):
        if company == "Company 2":
            raise QualificationInterpretationError(
                QualificationFailureCode.CONTRACT_WRONG_SHAPE,
                "Safe failure",
            )
        return replace(fixture, company=company, title=title)

    outcomes = EvaluateQualificationSample(runner).execute(
        postings=(_posting(1), _posting(2), _posting(3)),
        model_name="test-model",
        on_completed=lambda outcome, index, total: completed.append(
            (outcome, index, total)
        ),
        should_stop=lambda: False,
    )

    assert [outcome.succeeded for outcome in outcomes] == [True, False, True]
    assert "contract_wrong_shape" in outcomes[1].failure_message
    assert [(index, total) for _outcome, index, total in completed] == [
        (1, 3),
        (2, 3),
        (3, 3),
    ]


def test_batch_stop_is_checked_between_postings() -> None:
    fixture = load_review_fixtures()[1]
    stop = False

    def runner(_model, _title, _company, _content, _source_url):
        nonlocal stop
        stop = True
        return fixture

    outcomes = EvaluateQualificationSample(runner).execute(
        postings=(_posting(1), _posting(2)),
        model_name="test-model",
        on_completed=lambda *_args: None,
        should_stop=lambda: stop,
    )

    assert len(outcomes) == 1
