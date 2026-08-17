"""Validated shapes passed from document interpretation toward policy code."""

from dataclasses import dataclass

from junior.domain.facts import FactState
from junior.domain.qualifications import QualificationGroup, QualificationItem


@dataclass(frozen=True, slots=True)
class JobQualificationInterpretation:
    document_id: str
    schema_version: str
    interpreter_version: str
    section_state: FactState
    groups: tuple[QualificationGroup, ...]

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id is required")
        if not self.schema_version.strip():
            raise ValueError("schema_version is required")
        if not self.interpreter_version.strip():
            raise ValueError("interpreter_version is required")
        if self.section_state is FactState.STATED and not self.groups:
            raise ValueError("stated qualification sections require groups")
        if self.section_state in {
            FactState.NOT_STATED,
            FactState.UNREADABLE,
            FactState.NOT_APPLICABLE,
        } and self.groups:
            raise ValueError("unavailable qualification sections cannot contain groups")
        group_ids = [group.group_id for group in self.groups]
        if len(group_ids) != len(set(group_ids)):
            raise ValueError("interpretation contains duplicate group identifiers")


@dataclass(frozen=True, slots=True)
class ResumeQualificationInterpretation:
    document_id: str
    schema_version: str
    interpreter_version: str
    qualifications: tuple[QualificationItem, ...]

    def __post_init__(self) -> None:
        if not self.document_id.strip():
            raise ValueError("document_id is required")
        if not self.schema_version.strip():
            raise ValueError("schema_version is required")
        if not self.interpreter_version.strip():
            raise ValueError("interpreter_version is required")
        item_ids = [item.item_id for item in self.qualifications]
        if len(item_ids) != len(set(item_ids)):
            raise ValueError("resume contains duplicate qualification identifiers")
