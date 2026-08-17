"""Interfaces that keep models, collectors, storage, and UI replaceable."""

from collections.abc import Sequence
from typing import Protocol

from junior.domain.decisions import Decision
from junior.domain.documents import SourceDocument
from junior.domain.facts import ExtractedFact


class FactValidator(Protocol):
    def validate(
        self,
        document: SourceDocument,
        facts: Sequence[ExtractedFact],
    ) -> Sequence[ExtractedFact]: ...


class DecisionEngine(Protocol):
    def decide(self, facts: Sequence[ExtractedFact]) -> Decision: ...
