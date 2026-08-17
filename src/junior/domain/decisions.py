"""Deterministic outcome types produced by Junior policy, never by a model."""

from dataclasses import dataclass
from enum import StrEnum


class Recommendation(StrEnum):
    TOP_MATCH = "top_match"
    NEEDS_REVIEW = "needs_review"
    OMIT = "omit"


@dataclass(frozen=True, slots=True)
class Decision:
    recommendation: Recommendation
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.reasons:
            raise ValueError("every decision requires an auditable reason")
