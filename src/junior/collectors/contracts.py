"""Collector results must prove depth and job validity before persistence."""

from dataclasses import dataclass


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
