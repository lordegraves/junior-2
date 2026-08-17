"""Model assignment and routing kept behind task-specific application ports."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from junior.domain.company_discovery import (
    CompanyDiscoveryEvidence,
    CompanyDiscoveryProposal,
)
from junior.domain.documents import SourceDocument
from junior.domain.facts import ExtractedFact


class InterpretationTask(StrEnum):
    JOB_POSTING = "job_posting"
    RESUME = "resume"
    COMPANY_DISCOVERY = "company_discovery"


class ModelBackend(Protocol):
    @property
    def model_id(self) -> str: ...


@runtime_checkable
class DocumentModelBackend(Protocol):
    """A backend capable of normalized document interpretation."""

    @property
    def model_id(self) -> str: ...

    def interpret_document(
        self,
        task: InterpretationTask,
        document: SourceDocument,
    ) -> Sequence[ExtractedFact]: ...


@runtime_checkable
class CompanyDiscoveryModelBackend(Protocol):
    """A backend capable only of proposing bounded discovery actions."""

    @property
    def model_id(self) -> str: ...

    def propose_company_discovery(
        self,
        evidence: CompanyDiscoveryEvidence,
    ) -> CompanyDiscoveryProposal: ...


@dataclass(frozen=True, slots=True)
class TaskModelAssignments:
    """Application-owned task assignments; users never edit this mapping directly."""

    model_ids: Mapping[InterpretationTask, str]

    def __post_init__(self) -> None:
        copied = dict(self.model_ids)
        missing = set(InterpretationTask) - copied.keys()
        if missing:
            names = ", ".join(sorted(task.value for task in missing))
            raise ValueError(f"model assignments missing tasks: {names}")
        if any(not model_id.strip() for model_id in copied.values()):
            raise ValueError("model assignments require non-empty model identifiers")
        object.__setattr__(self, "model_ids", MappingProxyType(copied))

    @classmethod
    def shared(cls, model_id: str) -> "TaskModelAssignments":
        return cls({task: model_id for task in InterpretationTask})


class ModelRouter:
    """Select a backend by task without exposing model choice to callers."""

    def __init__(
        self,
        assignments: TaskModelAssignments,
        backends: Mapping[str, ModelBackend],
    ) -> None:
        self._assignments = assignments
        self._backends = dict(backends)
        required = set(assignments.model_ids.values())
        missing = required - self._backends.keys()
        if missing:
            names = ", ".join(sorted(missing))
            raise ValueError(f"model backends are not registered: {names}")
        for registered_id, backend in self._backends.items():
            if registered_id != backend.model_id:
                raise ValueError("registered model identifier does not match backend")

    def _backend_for(self, task: InterpretationTask) -> ModelBackend:
        model_id = self._assignments.model_ids[task]
        return self._backends[model_id]

    def document_backend_for(
        self, task: InterpretationTask
    ) -> DocumentModelBackend:
        if task is InterpretationTask.COMPANY_DISCOVERY:
            raise ValueError("company discovery is not a document task")
        backend = self._backend_for(task)
        if not isinstance(backend, DocumentModelBackend):
            raise TypeError(f"model {backend.model_id} cannot interpret documents")
        return backend

    def company_discovery_backend(self) -> CompanyDiscoveryModelBackend:
        backend = self._backend_for(InterpretationTask.COMPANY_DISCOVERY)
        if not isinstance(backend, CompanyDiscoveryModelBackend):
            message = f"model {backend.model_id} cannot propose discovery actions"
            raise TypeError(message)
        return backend
