from junior.domain.lifecycle import CandidateProfile, JobPosting
from junior.scoring.profile_constraints import evaluate_profile_constraints


def _posting(**changes) -> JobPosting:
    values = {
        "company_key": "acme",
        "company_name": "Acme",
        "source_type": "greenhouse",
        "source_url": "https://example/jobs/1",
        "title": "Senior Platform Engineer",
        "location": "Fort Collins, Colorado",
        "description": "Hybrid role with up to 10% travel.",
        "remote_status": "Hybrid",
    }
    values.update(changes)
    return JobPosting(**values)


def test_profile_constraints_match_explicit_practical_requirements() -> None:
    profile = CandidateProfile(
        "profile",
        "Candidate",
        seniority_levels=("Senior",),
        preferred_locations=("Fort Collins, Colorado",),
        work_arrangements=("Hybrid",),
        travel_tolerance=20,
    )

    result = evaluate_profile_constraints(_posting(), profile)

    assert not result.blockers
    assert result.location_status == "matched"
    assert "travel is within the configured limit" in result.matches


def test_profile_constraints_block_only_explicit_conflicts() -> None:
    profile = CandidateProfile(
        "profile",
        "Candidate",
        seniority_levels=("Mid-level",),
        preferred_locations=("Boulder, Colorado",),
        work_arrangements=("Remote",),
        on_call_preference="Not willing to participate",
        clearance_preference="Exclude jobs requiring an existing active clearance",
        travel_tolerance=5,
    )
    posting = _posting(
        description=(
            "Hybrid role with 25% travel and an on-call rotation. "
            "Active Secret clearance is required."
        )
    )

    result = evaluate_profile_constraints(posting, profile)

    assert result.location_status == "outside"
    assert len(result.blockers) == 6


def test_unknown_workplace_routes_to_review_instead_of_guessing() -> None:
    profile = CandidateProfile(
        "profile", "Candidate", work_arrangements=("Remote",)
    )

    result = evaluate_profile_constraints(
        _posting(remote_status=None, description="Build reliable services."), profile
    )

    assert not result.blockers
    assert result.review == ("workplace arrangement is not explicit",)


def test_profile_location_radius_matches_nearby_recognized_city() -> None:
    profile = CandidateProfile(
        "profile",
        "Candidate",
        preferred_locations=("Fort Collins, CO",),
        location_radius_miles=50,
    )

    result = evaluate_profile_constraints(
        _posting(
            location="Cheyenne, WY",
            remote_status=None,
            description="Build reliable services in Cheyenne, Wyoming.",
        ),
        profile,
    )

    assert result.location_status == "matched"


def test_unresolved_location_is_reviewable_not_a_false_conflict() -> None:
    profile = CandidateProfile(
        "profile",
        "Candidate",
        preferred_locations=("Fort Collins, CO",),
        location_radius_miles=25,
    )

    result = evaluate_profile_constraints(
        _posting(location="Northern region", remote_status=None), profile
    )

    assert result.location_status == "unknown"
    assert not result.blockers
