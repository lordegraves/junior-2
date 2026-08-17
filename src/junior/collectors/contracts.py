"""Common records that mature 1.x collectors will provide to Junior 2.0."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any, Protocol


@dataclass(frozen=True, slots=True)
class CollectorSource:
    company_id: str
    company_name: str
    source_type: str
    source_settings: Mapping[str, Any]

    def __post_init__(self) -> None:
        required = {
            "company_id": self.company_id,
            "company_name": self.company_name,
            "source_type": self.source_type,
        }
        for field_name, value in required.items():
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        object.__setattr__(
            self,
            "source_settings",
            MappingProxyType(dict(self.source_settings)),
        )


@dataclass(frozen=True, slots=True)
class CollectedJob:
    source_job_id: str
    company_id: str
    title: str
    location: str | None
    posting_url: str
    description: str | None

    def __post_init__(self) -> None:
        required = {
            "source_job_id": self.source_job_id,
            "company_id": self.company_id,
            "title": self.title,
            "posting_url": self.posting_url,
        }
        for field_name, value in required.items():
            if not value.strip():
                raise ValueError(f"{field_name} is required")


class JobCollector(Protocol):
    """The small interface each migrated 1.x collector must satisfy."""

    @property
    def source_type(self) -> str: ...

    def collect(self, source: CollectorSource) -> Sequence[CollectedJob]: ...


@dataclass(frozen=True, slots=True)
class CollectorValidation:
    jobs_found: int
    unique_job_ids: bool
    pagination_complete: bool
    descriptions_retrievable: bool

    @property
    def is_valid(self) -> bool:
        return (
            self.jobs_found > 0
            and self.unique_job_ids
            and self.pagination_complete
            and self.descriptions_retrievable
        )
