"""Typed evidence and proposals for bounded company-source discovery."""

from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class CompanyDiscoveryEvidence:
    """Safe public evidence supplied to discovery; never grants tool authority."""

    company_name: str
    submitted_url: str
    observed_urls: tuple[str, ...] = ()
    platform_fingerprints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not self.company_name.strip():
            raise ValueError("company_name is required")
        if not self.submitted_url.strip():
            raise ValueError("submitted_url is required")


class CompanyDiscoveryAction(StrEnum):
    FOLLOW_OFFICIAL_CAREERS_LINK = "follow_official_careers_link"
    INSPECT_KNOWN_PUBLIC_ENDPOINT = "inspect_known_public_endpoint"
    TEST_PAGINATION_PATTERN = "test_pagination_pattern"
    REQUEST_MORE_EVIDENCE = "request_more_evidence"
    NO_SUPPORTED_ACTION = "no_supported_action"


@dataclass(frozen=True, slots=True)
class CompanyDiscoveryProposal:
    """A proposal for deterministic code to validate, not an executable command."""

    action: CompanyDiscoveryAction
    target_url: str | None
    evidence_summary: str

    def __post_init__(self) -> None:
        if not self.evidence_summary.strip():
            raise ValueError("evidence_summary is required")
