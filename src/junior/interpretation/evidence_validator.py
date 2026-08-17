"""Reject model claims whose quoted evidence is not in the source document."""

from collections.abc import Sequence

from junior.domain.documents import EvidenceReference, SourceDocument
from junior.domain.facts import ExtractedFact, FactState


class EvidenceValidationError(ValueError):
    """An extracted claim cannot be traced to its declared source passage."""


def validate_evidence_reference(
    document: SourceDocument,
    evidence: EvidenceReference,
) -> None:
    """Apply the one exact-source check used by every interpretation path."""

    if evidence.document_id != document.document_id:
        raise EvidenceValidationError("evidence references another document")
    if evidence.document_version != document.version:
        raise EvidenceValidationError("evidence references another document version")
    source_quote = document.content[evidence.start : evidence.end]
    if source_quote != evidence.quote:
        raise EvidenceValidationError(
            "evidence quote does not match the source passage"
        )


class ExactEvidenceValidator:
    """Conservative baseline validator used before semantic checks are added."""

    def validate(
        self,
        document: SourceDocument,
        facts: Sequence[ExtractedFact],
    ) -> tuple[ExtractedFact, ...]:
        for fact in facts:
            for evidence in fact.evidence:
                validate_evidence_reference(document, evidence)
            if fact.state is FactState.STATED and not fact.evidence:
                raise EvidenceValidationError("stated fact has no evidence")
        return tuple(facts)
