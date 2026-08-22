"""Public posting records selected for repeatable interpretation evaluation."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class EvaluationPosting:
    posting_id: str
    company: str
    title: str
    description: str
    source_url: str
    sample_category: str


@dataclass(frozen=True, slots=True)
class EvaluationSample:
    source_build: str
    jobs_in_export: int
    eligible_jobs: int
    postings: tuple[EvaluationPosting, ...]
