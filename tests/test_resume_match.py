from junior.domain.lifecycle import CandidateProfile, JobPosting
from junior.scoring.resume_match import match_resume_to_posting


def _profile() -> CandidateProfile:
    return CandidateProfile(
        "default",
        "Candidate",
        core_strengths=(
            "Linux infrastructure",
            "HPC operations",
            "cluster systems",
            "datacenter operations",
        ),
        credible_adjacent=("SRE", "GPU infrastructure"),
        learning_or_gap=("production Kubernetes ownership", "security engineering"),
    )


def _posting(title: str, description: str) -> JobPosting:
    return JobPosting(
        "test",
        "Test",
        "greenhouse",
        "https://example/job",
        title,
        "Remote",
        description,
    )


def test_resume_match_preserves_strong_evidence_behavior() -> None:
    posting = _posting(
        "Senior Linux Infrastructure Engineer",
        "Linux infrastructure, HPC operations, cluster systems, datacenter operations.",
    )
    resume = (
        "Linux infrastructure, HPC operations, cluster systems, "
        "and datacenter operations."
    )

    result = match_resume_to_posting(posting, _profile(), resume)

    assert result.label == "Very Strong"
    assert result.evidence == _profile().core_strengths
    assert result.gaps == ()


def test_resume_match_preserves_gap_and_security_title_rules() -> None:
    result = match_resume_to_posting(
        _posting(
            "Senior SRE",
            "Linux infrastructure and production Kubernetes ownership.",
        ),
        _profile(),
        "Linux infrastructure and SRE experience.",
    )
    assert result.label == "Medium"
    assert result.gaps == ("production Kubernetes ownership",)

    adjacent = match_resume_to_posting(
        _posting(
            "Senior Platform Engineer",
            "Linux infrastructure partnering with security engineering teams.",
        ),
        _profile(),
        "Linux infrastructure experience.",
    )
    assert "security engineering" not in adjacent.gaps


def test_resume_match_is_unknown_without_profile_evidence() -> None:
    result = match_resume_to_posting(_posting("SRE", "Linux"), None, None)
    assert result.label == "Unknown"
    assert result.evidence == ()
