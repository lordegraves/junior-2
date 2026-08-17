"""Reject model claims whose quoted evidence is not in the source document."""

from collections.abc import Sequence

from junior.domain.documents import SourceDocument
from junior.domain.facts import ExtractedFact, FactState


class EvidenceValidationError(ValueError):
    """An extracted claim cannot be traced to its declared source passage."""


class ExactEvidenceValidator:
    """Conservative baseline validator used before semantic checks are added."""

    def validate(
        self,
        document: SourceDocument,
        facts: Sequence[ExtractedFact],
    ) -> tuple[ExtractedFact, ...]:
        for fact in facts:
            for evidence in fact.evidence:
                if evidence.document_id != document.document_id:
                    raise EvidenceValidationError(
                        "evidence references another document"
                    )
                source_quote = document.content[evidence.start : evidence.end]
                if source_quote != evidence.quote:
                    raise EvidenceValidationError(
                        "evidence quote does not match the source passage"
                    )
            if fact.state is FactState.STATED and not fact.evidence:
                raise EvidenceValidationError("stated fact has no evidence")
        return tuple(facts)
