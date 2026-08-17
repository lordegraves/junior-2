"""Normalized facts that keep uncertainty explicit instead of guessing."""

from dataclasses import dataclass
from enum import StrEnum
from typing import TypeAlias

from junior.domain.documents import EvidenceReference

JsonValue: TypeAlias = (
    str | int | float | bool | None | list["JsonValue"] | dict[str, "JsonValue"]
)


class FactState(StrEnum):
    STATED = "stated"
    NOT_STATED = "not_stated"
    AMBIGUOUS = "ambiguous"
    CONFLICTING = "conflicting"
    UNREADABLE = "unreadable"
    NOT_APPLICABLE = "not_applicable"


@dataclass(frozen=True, slots=True)
class ExtractedFact:
    name: str
    state: FactState
    value: JsonValue | None = None
    evidence: tuple[EvidenceReference, ...] = ()
    interpreter_version: str = "unversioned"
    schema_version: str = "1"

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("fact name is required")
        if self.state is FactState.STATED and not self.evidence:
            raise ValueError("stated facts require evidence")
        if self.state is FactState.NOT_STATED and self.value is not None:
            raise ValueError("a not-stated fact cannot have an inferred value")
