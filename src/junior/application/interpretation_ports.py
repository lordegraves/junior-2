"""Task-specific interpretation interfaces used by application workflows."""

from collections.abc import Sequence
from typing import Protocol

from junior.domain.company_discovery import (
    CompanyDiscoveryEvidence,
    CompanyDiscoveryProposal,
)
from junior.domain.documents import SourceDocument
from junior.domain.facts import ExtractedFact


class JobPostingInterpreter(Protocol):
    def interpret_job_posting(
        self, document: SourceDocument
    ) -> Sequence[ExtractedFact]: ...


class ResumeInterpreter(Protocol):
    def interpret_resume(self, document: SourceDocument) -> Sequence[ExtractedFact]: ...


class CompanyDiscoveryAssistant(Protocol):
    def propose_company_discovery(
        self, evidence: CompanyDiscoveryEvidence
    ) -> CompanyDiscoveryProposal: ...
