from typing import Any

import pytest

from junior.application.interpret_qualification_review import (
    InterpretQualificationReview,
    QualificationFailureCode,
    QualificationInterpretationError,
)
from junior.domain.documents import SourceDocument
from junior.interpretation.qualification_evidence_validator import (
    QualificationEvidenceValidator,
)


class FixedBackend:
    model_id = "test-model"

    def __init__(self, payload: dict[str, Any]) -> None:
        self.payload = payload

    def propose_job_qualifications(
        self, document: SourceDocument
    ) -> dict[str, Any]:
        return self.payload

    def review_job_qualification_semantics(
        self,
        document: SourceDocument,
        proposed: dict[str, Any],
    ) -> dict[str, Any]:
        return proposed


def _payload(quote: str, start: int, end: int) -> dict[str, Any]:
    return {
        "schema_version": "1",
        "interpreter_version": "test-model-1",
        "section_state": "stated",
        "groups": [
            {
                "group_id": "key_qualifications",
                "priority": "required",
                "paths": [
                    {
                        "path_id": "required_path",
                        "requirements": [
                            {
                                "item_id": "python",
                                "category": "skill",
                                "statement": "Python",
                                "normalized_value": "python",
                                "state": "stated",
                                "evidence": [
                                    {"quote": quote, "start": start, "end": end}
                                ],
                                "confidence": 0.9,
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_live_interpretation_validates_evidence_before_review() -> None:
    service = InterpretQualificationReview(
        FixedBackend(_payload("Python", 0, 6)),
        QualificationEvidenceValidator(),
    )

    result = service.execute(
        title="Engineer", company="Example", content="Python required"
    )

    assert result.groups[0].paths[0].requirements[0].label == "Python"
    assert result.technical_details[-1] == (
        "Mode",
        "Two-pass local model review — test-model",
    )
    assert "not connected" in result.engine_message.casefold()
    assert "did not compare a résumé" in result.engine_message


def test_live_interpretation_rejects_false_model_evidence() -> None:
    service = InterpretQualificationReview(
        FixedBackend(_payload("Kubernetes", 0, 10)),
        QualificationEvidenceValidator(),
    )

    with pytest.raises(QualificationInterpretationError, match="evidence_not_found"):
        service.execute(title="Engineer", company="Example", content="Python required")


def test_live_interpretation_reports_contract_failure_separately() -> None:
    service = InterpretQualificationReview(
        FixedBackend({"not": "the contract"}),
        QualificationEvidenceValidator(),
    )

    with pytest.raises(QualificationInterpretationError) as captured:
        service.execute(title="Engineer", company="Example", content="Python required")

    assert captured.value.code is QualificationFailureCode.CONTRACT_MISSING_FIELD
    assert "contract_missing_field" in str(captured.value)


def test_carvana_review_keeps_full_posting_but_displays_only_requirements() -> None:
    content = (
        "We're the fastest-growing used automotive retailer.\n"
        "Benefits + Perks: paid healthcare and a 401(k).\n"
        "About the Role:\n"
        "Deliver vehicles straight to customers' doors.\n"
        "General qualifications and requirements\n"
        "Must be able to read, write, speak and understand English."
    )
    quotes = [
        "We're the fastest-growing used automotive retailer.",
        "Benefits + Perks: paid healthcare and a 401(k).",
        "Deliver vehicles straight to customers' doors.",
        "Must be able to read, write, speak and understand English.",
    ]
    payload = _payload(quotes[0], 0, len(quotes[0]))
    requirements = payload["groups"][0]["paths"][0]["requirements"]
    requirements.clear()
    for index, quote in enumerate(quotes):
        start = content.index(quote)
        requirements.append(
            {
                "item_id": f"candidate_{index}",
                "category": "other",
                "statement": quote,
                "normalized_value": None,
                "state": "stated",
                "evidence": [
                    {"quote": quote, "start": start, "end": start + len(quote)}
                ],
                "confidence": 0.9,
            }
        )
    service = InterpretQualificationReview(
        FixedBackend(payload), QualificationEvidenceValidator()
    )

    result = service.execute(
        title="Customer Service Delivery Advocate",
        company="Carvana",
        content=content,
    )

    assert result.source_document.content == content
    displayed = [
        requirement.label
        for group in result.groups
        for path in group.paths
        for requirement in path.requirements
    ]
    assert displayed == [quotes[-1]]
