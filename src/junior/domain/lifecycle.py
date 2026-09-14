"""Durable records shared by Junior's native workflows."""

from dataclasses import dataclass


@dataclass(frozen=True)
class CandidateProfile:
    profile_id: str
    name: str
    compensation_floor_usd: int | None = None
    preferred_base_usd: int | None = None
    resume_source_path: str | None = None
    resume_normalized_text_path: str | None = None
    core_strengths: tuple[str, ...] = ()
    credible_adjacent: tuple[str, ...] = ()
    learning_or_gap: tuple[str, ...] = ()
    avoid: tuple[str, ...] = ()
    target_roles: tuple[str, ...] = ()
    seniority_levels: tuple[str, ...] = ()
    preferred_locations: tuple[str, ...] = ()
    location_radius_miles: int = 25
    work_arrangements: tuple[str, ...] = ()
    employment_types: tuple[str, ...] = ()
    schedule_preference: str = "Any schedule"
    on_call_preference: str = "Review each job"
    clearance_preference: str = "Review each job"
    travel_tolerance: int | None = None
    include_strong_location_outliers: bool = False
    fit_signals: tuple[tuple[str, str, str], ...] = ()


@dataclass(frozen=True)
class JobPosting:
    company_key: str
    company_name: str
    source_type: str
    source_url: str
    title: str
    location: str | None = None
    description: str | None = None
    source_job_id: str | None = None
    remote_status: str | None = None
    salary_text: str | None = None


@dataclass(frozen=True)
class ApplicationRecord:
    job_radar_id: str
    company_name: str
    role_title: str
    source_url: str | None = None
    status: str = "review_needed"
    follow_up_on: str | None = None
    outcome: str | None = None
    notes: str | None = None
    applied_on: str | None = None
    last_activity_on: str | None = None


@dataclass(frozen=True)
class LegacyImportSummary:
    source_path: str
    imported: bool
    table_counts: tuple[tuple[str, int], ...]
