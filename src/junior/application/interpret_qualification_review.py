"""Turn a model qualification proposal into a safe review record."""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol
from uuid import uuid4

from junior.application.review_workspace import (
    ReviewValidationState,
    ReviewWorkspaceResult,
    build_review_workspace_result,
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
    parse_job_qualification_output,
)
from junior.interpretation.qualification_semantic_guardrails import (
    apply_explicit_category_guardrails,
)


class QualificationProposalBackend(Protocol):
    @property
    def model_id(self) -> str: ...

    def propose_job_qualifications(
        self, document: SourceDocument
    ) -> dict[str, Any]: ...

    def review_job_qualification_semantics(
        self,
        document: SourceDocument,
        proposed: dict[str, Any],
    ) -> dict[str, Any]: ...


class QualificationFailureCode(StrEnum):
    CONTRACT_MISSING_FIELD = "contract_missing_field"
    CONTRACT_EXTRA_FIELD = "contract_extra_field"
    CONTRACT_INVALID_VALUE = "contract_invalid_value"
    CONTRACT_EMPTY_STRUCTURE = "contract_empty_structure"
    CONTRACT_DUPLICATE_IDENTIFIER = "contract_duplicate_identifier"
    CONTRACT_WRONG_SHAPE = "contract_wrong_shape"
    EVIDENCE_NOT_FOUND = "evidence_not_found"
    EVIDENCE_WRONG_DOCUMENT = "evidence_wrong_document"
    EVIDENCE_INVALID_LOCATION = "evidence_invalid_location"
    UNKNOWN_CONTRACT_FAILURE = "unknown_contract_failure"


class QualificationInterpretationError(RuntimeError):
    """A categorized failure safe to show without source or model output."""

    def __init__(self, code: QualificationFailureCode, message: str) -> None:
        self.code = code
        super().__init__(f"{message} Reference: {code.value}.")


@dataclass(slots=True)
class InterpretQualificationReview:
    backend: QualificationProposalBackend
    validator: QualificationEvidenceValidator

    def execute(
        self,
        *,
        title: str,
        company: str,
        content: str,
        source_uri: str | None = None,
    ) -> ReviewWorkspaceResult:
        document = SourceDocument(
            document_id=f"interactive-{uuid4()}",
            kind=DocumentKind.JOB_POSTING,
            content=content,
            source_uri=source_uri,
        )
        payload = self.backend.propose_job_qualifications(document)
        payload = apply_explicit_category_guardrails(payload, document.content)
        payload = self._validate_payload(document, payload, "extraction")
        payload = self.backend.review_job_qualification_semantics(document, payload)
        payload = apply_explicit_category_guardrails(payload, document.content)
        payload = self._validate_payload(document, payload, "semantic review")
        interpretation = parse_job_qualification_output(document, payload)

        return build_review_workspace_result(
            fixture_id=document.document_id,
            title=title.strip() or "Pasted job posting",
            company=company.strip() or "Unspecified company",
            source_document=document,
            interpretation=interpretation,
            validation_state=ReviewValidationState.VALIDATED,
            validation_message=(
                "Every displayed qualification has exact source evidence and "
                "completed a separate semantic review."
            ),
            mode=f"Two-pass local model review — {self.backend.model_id}",
            engine_message=(
                "Not connected. Interpretation and semantic review completed, but "
                "Junior did not compare a résumé, score, recommend, or omit this job."
            ),
        )

    def _validate_payload(
        self,
        document: SourceDocument,
        payload: dict[str, Any],
        stage: str,
    ) -> dict[str, Any]:
        payload = resolve_unique_evidence_offsets(payload, document.content)
        try:
            interpretation = parse_job_qualification_output(document, payload)
        except QualificationOutputError as exc:
            code = _classify_contract_failure(str(exc))
            raise QualificationInterpretationError(
                code,
                f"The local model's {stage} did not match Junior's required format. "
                "No model claims were accepted."
            ) from exc
        try:
            self.validator.validate_job(document, interpretation)
        except EvidenceValidationError as exc:
            code = _classify_evidence_failure(str(exc))
            raise QualificationInterpretationError(
                code,
                f"The local model's {stage} included evidence that could not be "
                "verified in the posting. No model claims were accepted."
            ) from exc
        return payload


def _classify_contract_failure(message: str) -> QualificationFailureCode:
    lowered = message.casefold()
    if "missing fields" in lowered:
        return QualificationFailureCode.CONTRACT_MISSING_FIELD
    if "unsupported fields" in lowered:
        return QualificationFailureCode.CONTRACT_EXTRA_FIELD
    if "duplicate" in lowered:
        return QualificationFailureCode.CONTRACT_DUPLICATE_IDENTIFIER
    if "require" in lowered and (
        "groups" in lowered or "path" in lowered or "item" in lowered
    ):
        return QualificationFailureCode.CONTRACT_EMPTY_STRUCTURE
    if "must be" in lowered:
        return QualificationFailureCode.CONTRACT_WRONG_SHAPE
    if "unsupported" in lowered or "confidence" in lowered:
        return QualificationFailureCode.CONTRACT_INVALID_VALUE
    return QualificationFailureCode.UNKNOWN_CONTRACT_FAILURE


def _classify_evidence_failure(message: str) -> QualificationFailureCode:
    lowered = message.casefold()
    if "another document" in lowered or "document version" in lowered:
        return QualificationFailureCode.EVIDENCE_WRONG_DOCUMENT
    if "does not match" in lowered:
        return QualificationFailureCode.EVIDENCE_NOT_FOUND
    return QualificationFailureCode.EVIDENCE_INVALID_LOCATION
