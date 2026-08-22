"""Presentation-ready qualification review records with no GUI dependency."""

from dataclasses import dataclass
from enum import StrEnum

from junior.domain.document_interpretations import (
    JobQualificationInterpretation,
    ResumeQualificationInterpretation,
)
from junior.domain.documents import EvidenceReference, SourceDocument
from junior.domain.facts import JsonValue
from junior.domain.qualifications import RequirementPriority


class ReviewValidationState(StrEnum):
    VALIDATED = "validated"
    NEEDS_REVIEW = "needs_review"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RequirementReview:
    label: str
    category: str
    state: str
    confidence: float
    evidence: tuple[EvidenceReference, ...]
    normalized_value: JsonValue = None


@dataclass(frozen=True, slots=True)
class QualificationPathReview:
    label: str
    requirements: tuple[RequirementReview, ...]


@dataclass(frozen=True, slots=True)
class QualificationGroupReview:
    label: str
    priority: RequirementPriority
    paths: tuple[QualificationPathReview, ...]


@dataclass(frozen=True, slots=True)
class ReviewWorkspaceResult:
    fixture_id: str
    title: str
    company: str
    source_document: SourceDocument
    section_state: str
    groups: tuple[QualificationGroupReview, ...]
    validation_state: ReviewValidationState
    validation_message: str
    engine_message: str
    rejected_claims: tuple[str, ...]
    technical_details: tuple[tuple[str, str], ...]
    document_kind: str = "job"


def build_review_workspace_result(
    *,
    fixture_id: str,
    title: str,
    company: str,
    source_document: SourceDocument,
    interpretation: JobQualificationInterpretation,
    validation_state: ReviewValidationState,
    validation_message: str,
    rejected_claims: tuple[str, ...] = (),
    mode: str = "Fixture preview — no model was run",
    engine_message: str | None = None,
) -> ReviewWorkspaceResult:
    groups = tuple(
        QualificationGroupReview(
            label=group.group_id.replace("_", " ").title(),
            priority=group.priority,
            paths=tuple(
                QualificationPathReview(
                    label=path.path_id.replace("_", " ").title(),
                    requirements=tuple(
                        RequirementReview(
                            label=requirement.statement,
                            category=requirement.category.value.replace(
                                "_", " "
                            ).title(),
                            state=requirement.state.value,
                            confidence=requirement.confidence,
                            evidence=requirement.evidence,
                            normalized_value=requirement.normalized_value,
                        )
                        for requirement in path.requirements
                    ),
                )
                for path in group.paths
            ),
        )
        for group in interpretation.groups
    )
    return ReviewWorkspaceResult(
        fixture_id=fixture_id,
        title=title,
        company=company,
        source_document=source_document,
        section_state=interpretation.section_state.value,
        groups=groups,
        validation_state=validation_state,
        validation_message=validation_message,
        engine_message=engine_message
        or (
            "Not connected in this preview. The existing Junior 1.x rules will be "
            "connected through the shadow-test adapter next."
        ),
        rejected_claims=rejected_claims,
        technical_details=tuple(
            item
            for item in (
                ("Contract version", interpretation.schema_version),
                ("Interpreter", interpretation.interpreter_version),
                ("Document ID", source_document.document_id),
                ("Document version", source_document.version),
                ("Source URL", source_document.source_uri),
                ("Mode", mode),
            )
            if item[1] is not None
        ),
    )


def build_resume_review_workspace_result(
    *,
    filename: str,
    source_document: SourceDocument,
    interpretation: ResumeQualificationInterpretation,
    validation_state: ReviewValidationState,
    validation_message: str,
    mode: str,
) -> ReviewWorkspaceResult:
    requirements = tuple(
        RequirementReview(
            label=item.statement,
            category=item.category.value.replace("_", " ").title(),
            state=item.state.value,
            confidence=item.confidence,
            evidence=item.evidence,
            normalized_value=item.normalized_value,
        )
        for item in interpretation.qualifications
    )
    groups = (
        (
            QualificationGroupReview(
                label="Resume Qualifications",
                priority=RequirementPriority.REQUIRED,
                paths=(QualificationPathReview("Evidence-backed items", requirements),),
            ),
        )
        if requirements
        else ()
    )
    return ReviewWorkspaceResult(
        fixture_id=source_document.document_id,
        title=filename,
        company="Resume",
        source_document=source_document,
        section_state="stated" if requirements else "not_stated",
        groups=groups,
        validation_state=validation_state,
        validation_message=validation_message,
        engine_message="Not connected. Junior did not match or score this resume.",
        rejected_claims=(),
        technical_details=(
            ("Contract version", interpretation.schema_version),
            ("Interpreter", interpretation.interpreter_version),
            ("Document ID", source_document.document_id),
            ("Mode", mode),
        ),
        document_kind="resume",
    )
