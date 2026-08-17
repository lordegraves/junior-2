"""Task-specific services backed by configurable local-model routing."""

from junior.domain.company_discovery import (
    CompanyDiscoveryEvidence,
    CompanyDiscoveryProposal,
)
from junior.domain.documents import DocumentKind, SourceDocument
from junior.domain.facts import ExtractedFact
from junior.interpretation.model_routing import InterpretationTask, ModelRouter


class RoutedDocumentInterpreter:
    """Share document plumbing while preserving distinct task entry points."""

    def __init__(self, router: ModelRouter) -> None:
        self._router = router

    def interpret_job_posting(
        self, document: SourceDocument
    ) -> tuple[ExtractedFact, ...]:
        return self._interpret(
            document,
            expected_kind=DocumentKind.JOB_POSTING,
            task=InterpretationTask.JOB_POSTING,
        )

    def interpret_resume(self, document: SourceDocument) -> tuple[ExtractedFact, ...]:
        return self._interpret(
            document,
            expected_kind=DocumentKind.RESUME,
            task=InterpretationTask.RESUME,
        )

    def _interpret(
        self,
        document: SourceDocument,
        *,
        expected_kind: DocumentKind,
        task: InterpretationTask,
    ) -> tuple[ExtractedFact, ...]:
        if document.kind is not expected_kind:
            raise ValueError(f"{task.value} requires a {expected_kind.value} document")
        backend = self._router.document_backend_for(task)
        return tuple(backend.interpret_document(task, document))


class RoutedCompanyDiscoveryAssistant:
    def __init__(self, router: ModelRouter) -> None:
        self._router = router

    def propose_company_discovery(
        self, evidence: CompanyDiscoveryEvidence
    ) -> CompanyDiscoveryProposal:
        backend = self._router.company_discovery_backend()
        return backend.propose_company_discovery(evidence)
