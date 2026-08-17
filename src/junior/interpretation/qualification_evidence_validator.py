"""Validate every job requirement and résumé qualification against its source."""

from collections.abc import Iterable

from junior.domain.document_interpretations import (
    JobQualificationInterpretation,
    ResumeQualificationInterpretation,
)
from junior.domain.documents import SourceDocument
from junior.domain.qualifications import QualificationItem
from junior.interpretation.evidence_validator import (
    EvidenceValidationError,
    validate_evidence_reference,
)


class QualificationEvidenceValidator:
    def validate_job(
        self,
        document: SourceDocument,
        interpretation: JobQualificationInterpretation,
    ) -> JobQualificationInterpretation:
        if interpretation.document_id != document.document_id:
            raise EvidenceValidationError("interpretation references another document")
        items = (
            requirement
            for group in interpretation.groups
            for path in group.paths
            for requirement in path.requirements
        )
        self._validate_items(document, items)
        return interpretation

    def validate_resume(
        self,
        document: SourceDocument,
        interpretation: ResumeQualificationInterpretation,
    ) -> ResumeQualificationInterpretation:
        if interpretation.document_id != document.document_id:
            raise EvidenceValidationError("interpretation references another document")
        self._validate_items(document, interpretation.qualifications)
        return interpretation

    def _validate_items(
        self,
        document: SourceDocument,
        items: Iterable[QualificationItem],
    ) -> None:
        for item in items:
            for evidence in item.evidence:
                validate_evidence_reference(document, evidence)
