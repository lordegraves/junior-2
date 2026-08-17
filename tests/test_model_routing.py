from dataclasses import dataclass, field

from junior.domain.company_discovery import (
    CompanyDiscoveryAction,
    CompanyDiscoveryEvidence,
    CompanyDiscoveryProposal,
)
from junior.domain.documents import DocumentKind, SourceDocument
from junior.domain.facts import ExtractedFact
from junior.interpretation.model_routing import (
    InterpretationTask,
    ModelRouter,
    TaskModelAssignments,
)
from junior.interpretation.routed_services import (
    RoutedCompanyDiscoveryAssistant,
    RoutedDocumentInterpreter,
)


@dataclass
class RecordingBackend:
    model_id: str
    calls: list[InterpretationTask] = field(default_factory=list)

    def interpret_document(
        self,
        task: InterpretationTask,
        document: SourceDocument,
    ) -> tuple[ExtractedFact, ...]:
        self.calls.append(task)
        return ()

    def propose_company_discovery(
        self,
        evidence: CompanyDiscoveryEvidence,
    ) -> CompanyDiscoveryProposal:
        self.calls.append(InterpretationTask.COMPANY_DISCOVERY)
        return CompanyDiscoveryProposal(
            CompanyDiscoveryAction.REQUEST_MORE_EVIDENCE,
            evidence.submitted_url,
            "More public evidence is required.",
        )


@dataclass
class RecordingDiscoveryBackend:
    """A specialist proves dedicated models need only their assigned capability."""

    model_id: str
    calls: list[InterpretationTask] = field(default_factory=list)

    def propose_company_discovery(
        self,
        evidence: CompanyDiscoveryEvidence,
    ) -> CompanyDiscoveryProposal:
        self.calls.append(InterpretationTask.COMPANY_DISCOVERY)
        return CompanyDiscoveryProposal(
            CompanyDiscoveryAction.REQUEST_MORE_EVIDENCE,
            evidence.submitted_url,
            "More public evidence is required.",
        )


def test_all_tasks_can_share_one_model_backend() -> None:
    shared = RecordingBackend("shared-interpreter")
    router = ModelRouter(
        TaskModelAssignments.shared(shared.model_id),
        {shared.model_id: shared},
    )
    documents = RoutedDocumentInterpreter(router)
    discovery = RoutedCompanyDiscoveryAssistant(router)

    documents.interpret_job_posting(
        SourceDocument("job-1", DocumentKind.JOB_POSTING, "A job posting")
    )
    documents.interpret_resume(
        SourceDocument("resume-1", DocumentKind.RESUME, "A resume")
    )
    discovery.propose_company_discovery(
        CompanyDiscoveryEvidence("Example", "https://example.com/careers")
    )

    assert shared.calls == list(InterpretationTask)


def test_one_task_can_move_to_a_dedicated_model_without_changing_callers() -> None:
    shared = RecordingBackend("shared-interpreter")
    discovery_model = RecordingDiscoveryBackend("discovery-specialist")
    assignments = TaskModelAssignments(
        {
            InterpretationTask.JOB_POSTING: shared.model_id,
            InterpretationTask.RESUME: shared.model_id,
            InterpretationTask.COMPANY_DISCOVERY: discovery_model.model_id,
        }
    )
    router = ModelRouter(
        assignments,
        {
            shared.model_id: shared,
            discovery_model.model_id: discovery_model,
        },
    )

    RoutedDocumentInterpreter(router).interpret_job_posting(
        SourceDocument("job-1", DocumentKind.JOB_POSTING, "A job posting")
    )
    RoutedCompanyDiscoveryAssistant(router).propose_company_discovery(
        CompanyDiscoveryEvidence("Example", "https://example.com/careers")
    )

    assert shared.calls == [InterpretationTask.JOB_POSTING]
    assert discovery_model.calls == [InterpretationTask.COMPANY_DISCOVERY]
