"""Turn a local-model resume proposal into an evidence-backed review."""

from dataclasses import dataclass
from typing import Any, Protocol
from uuid import uuid4

from junior.application.review_workspace import (
    ReviewValidationState,
    ReviewWorkspaceResult,
    build_resume_review_workspace_result,
)
from junior.domain.documents import DocumentKind, SourceDocument
from junior.interpretation.evidence_validator import EvidenceValidationError
from junior.interpretation.qualification_evidence_resolver import (
    resolve_unique_evidence_offsets,
)
from junior.interpretation.qualification_evidence_validator import (
    QualificationEvidenceValidator,
)
from junior.interpretation.qualification_output_parser import (
    QualificationOutputError,
    parse_resume_qualification_output,
)
from junior.interpretation.qualification_semantic_guardrails import (
    apply_resume_qualification_guardrails,
)


class ResumeProposalBackend(Protocol):
    @property
    def model_id(self) -> str: ...

    def propose_resume_qualifications(
        self, document: SourceDocument
    ) -> dict[str, Any]: ...


@dataclass(slots=True)
class InterpretResumeReview:
    backend: ResumeProposalBackend
    validator: QualificationEvidenceValidator

    def execute(self, *, filename: str, content: str) -> ReviewWorkspaceResult:
        document = SourceDocument(
            document_id=f"resume-{uuid4()}",
            kind=DocumentKind.RESUME,
            content=content,
        )
        payload = self.backend.propose_resume_qualifications(document)
        payload = apply_resume_qualification_guardrails(payload, document.content)
        payload = resolve_unique_evidence_offsets(payload, document.content)
        try:
            interpretation = parse_resume_qualification_output(document, payload)
            self.validator.validate_resume(document, interpretation)
        except (QualificationOutputError, EvidenceValidationError) as exc:
            raise ValueError(
                "The local model's resume extraction failed Junior's contract or "
                "exact-evidence check. No model claims were accepted."
            ) from exc
        return build_resume_review_workspace_result(
            filename=filename,
            source_document=document,
            interpretation=interpretation,
            validation_state=ReviewValidationState.VALIDATED,
            validation_message=(
                "Every displayed resume qualification has exact source evidence."
            ),
            mode=f"Local resume interpretation — {self.backend.model_id}",
        )
