from typing import Any

from junior.application.interpret_resume_review import InterpretResumeReview
from junior.domain.documents import SourceDocument
from junior.interpretation.qualification_evidence_validator import (
    QualificationEvidenceValidator,
)


class FixedResumeBackend:
    model_id = "test-model"

    def propose_resume_qualifications(
        self, document: SourceDocument
    ) -> dict[str, Any]:
        quote = "Built Python services"
        start = document.content.index(quote)
        return {
            "schema_version": "1",
            "interpreter_version": "test-resume-1",
            "qualifications": [
                {
                    "item_id": "python",
                    "category": "skill",
                    "statement": quote,
                    "normalized_value": "python",
                    "state": "stated",
                    "evidence": [
                        {"quote": quote, "start": start, "end": start + len(quote)}
                    ],
                    "confidence": 0.9,
                }
            ],
        }


def test_resume_review_keeps_full_source_and_verified_qualifications() -> None:
    content = "Clayton Example\nBuilt Python services\nEducation details"
    service = InterpretResumeReview(
        FixedResumeBackend(), QualificationEvidenceValidator()
    )

    result = service.execute(filename="resume.docx", content=content)

    assert result.document_kind == "resume"
    assert result.source_document.content == content
    assert result.groups[0].paths[0].requirements[0].label == "Built Python services"
    assert "did not match or score" in result.engine_message
