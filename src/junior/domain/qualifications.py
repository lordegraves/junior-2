"""Qualification records that preserve alternatives and source evidence."""

from dataclasses import dataclass
from enum import StrEnum

from junior.domain.documents import EvidenceReference
from junior.domain.facts import FactState, JsonValue


class QualificationCategory(StrEnum):
    EDUCATION = "education"
    EXPERIENCE = "experience"
    SKILL = "skill"
    CERTIFICATION = "certification"
    WORK_AUTHORIZATION = "work_authorization"
    SECURITY_CLEARANCE = "security_clearance"
    PHYSICAL = "physical"
    TRAVEL = "travel"
    SCHEDULE = "schedule"
    OTHER = "other"


class RequirementPriority(StrEnum):
    REQUIRED = "required"
    PREFERRED = "preferred"


@dataclass(frozen=True, slots=True)
class QualificationItem:
    """One job requirement or one qualification stated by a résumé."""

    item_id: str
    category: QualificationCategory
    statement: str
    normalized_value: JsonValue
    state: FactState
    evidence: tuple[EvidenceReference, ...]
    confidence: float

    def __post_init__(self) -> None:
        if not self.item_id.strip():
            raise ValueError("qualification item_id is required")
        if not self.statement.strip():
            raise ValueError("qualification statement is required")
        if self.state in {FactState.NOT_STATED, FactState.NOT_APPLICABLE}:
            raise ValueError("qualification items must describe source content")
        if not self.evidence:
            raise ValueError("qualification items require source evidence")
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("qualification confidence must be between 0 and 1")


@dataclass(frozen=True, slots=True)
class QualificationPath:
    """Requirements that must all be satisfied within one acceptable path."""

    path_id: str
    requirements: tuple[QualificationItem, ...]

    def __post_init__(self) -> None:
        if not self.path_id.strip():
            raise ValueError("qualification path_id is required")
        if not self.requirements:
            raise ValueError("qualification path requires at least one item")
        item_ids = [item.item_id for item in self.requirements]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("qualification path contains duplicate item identifiers")


@dataclass(frozen=True, slots=True)
class QualificationGroup:
    """Alternative paths where satisfying any one path satisfies the group."""

    group_id: str
    priority: RequirementPriority
    paths: tuple[QualificationPath, ...]

    def __post_init__(self) -> None:
        if not self.group_id.strip():
            raise ValueError("qualification group_id is required")
        if not self.paths:
            raise ValueError("qualification group requires at least one path")
        path_ids = [path.path_id for path in self.paths]
        if len(path_ids) != len(set(path_ids)):
            raise ValueError("qualification group contains duplicate path identifiers")
