from dataclasses import dataclass

import pytest

from junior.application.interpret_job import InterpretJobPosting
from junior.domain.decisions import Recommendation
from junior.domain.documents import DocumentKind, EvidenceReference, SourceDocument
from junior.domain.facts import ExtractedFact, FactState
from junior.interpretation.evidence_validator import (
    EvidenceValidationError,
    ExactEvidenceValidator,
)
from junior.scoring.baseline import ConservativeDecisionEngine


@dataclass
class StubInterpreter:
    fact: ExtractedFact

    def interpret(self, document: SourceDocument) -> tuple[ExtractedFact, ...]:
        return (self.fact,)


def test_validated_fact_reaches_deterministic_engine() -> None:
    content = "This position may be performed remotely in the United States."
    document = SourceDocument("job-1", DocumentKind.JOB_POSTING, content)
    quote = "performed remotely"
    start = content.index(quote)
    fact = ExtractedFact(
        name="workplace_arrangement",
        state=FactState.STATED,
        value="remote",
        evidence=(EvidenceReference("job-1", quote, start, start + len(quote)),),
    )
    use_case = InterpretJobPosting(
        StubInterpreter(fact),
        ExactEvidenceValidator(),
        ConservativeDecisionEngine(),
    )

    decision = use_case.execute(document)

    assert decision.recommendation is Recommendation.NEEDS_REVIEW
    assert decision.reasons == (
        "Validated facts require deterministic profile evaluation.",
    )


def test_unsupported_interpreter_claim_never_reaches_scoring() -> None:
    document = SourceDocument(
        "job-2",
        DocumentKind.JOB_POSTING,
        "Compensation is not listed.",
    )
    fact = ExtractedFact(
        name="compensation",
        state=FactState.STATED,
        value={"minimum": 150000, "currency": "USD"},
        evidence=(EvidenceReference("job-2", "$150,000", 0, 8),),
    )
    use_case = InterpretJobPosting(
        StubInterpreter(fact),
        ExactEvidenceValidator(),
        ConservativeDecisionEngine(),
    )

    with pytest.raises(EvidenceValidationError):
        use_case.execute(document)


def test_missing_compensation_stays_missing() -> None:
    fact = ExtractedFact(
        name="compensation",
        state=FactState.NOT_STATED,
    )

    assert fact.value is None
    assert fact.evidence == ()
