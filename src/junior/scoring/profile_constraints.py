"""Conservative deterministic checks for user-owned practical constraints."""

from __future__ import annotations

import re
from dataclasses import dataclass

from junior.domain.lifecycle import CandidateProfile, JobPosting
from junior.infrastructure.reference_catalog import distance_miles, resolve_location


@dataclass(frozen=True, slots=True)
class ConstraintResult:
    blockers: tuple[str, ...] = ()
    review: tuple[str, ...] = ()
    matches: tuple[str, ...] = ()
    location_status: str = "unknown"


def evaluate_profile_constraints(
    posting: JobPosting, profile: CandidateProfile | None
) -> ConstraintResult:
    if profile is None:
        return ConstraintResult()
    text = " ".join(
        filter(None, (posting.title, posting.location, posting.description))
    ).casefold()
    blockers: list[str] = []
    review: list[str] = []
    matches: list[str] = []

    arrangement = _arrangement(posting, text)
    accepted_arrangements = {value.casefold() for value in profile.work_arrangements}
    if accepted_arrangements and arrangement:
        if arrangement.casefold() in accepted_arrangements:
            matches.append(f"workplace arrangement: {arrangement}")
        else:
            blockers.append(f"workplace arrangement is {arrangement}")
    elif accepted_arrangements:
        review.append("workplace arrangement is not explicit")

    location_status = _location_status(posting, profile, arrangement)
    if location_status == "outside":
        message = "location is outside the configured areas"
        destination = (
            review if profile.include_strong_location_outliers else blockers
        )
        destination.append(message)
    elif location_status == "matched":
        matches.append("location matches the configured areas")

    if profile.on_call_preference == "Not willing to participate" and re.search(
        r"\bon[- ]call\b|pager rotation", text
    ):
        blockers.append("on-call work conflicts with the profile")
    if (
        profile.clearance_preference
        == "Exclude jobs requiring an existing active clearance"
        and re.search(r"active\s+(?:secret|top secret|ts/sci).*required", text)
    ):
        blockers.append("an existing active security clearance is required")

    travel = _required_travel(text)
    if travel is not None and profile.travel_tolerance is not None:
        if travel > profile.travel_tolerance:
            blockers.append(
                f"required travel ({travel}%) exceeds the profile limit "
                f"({profile.travel_tolerance}%)"
            )
        else:
            matches.append("travel is within the configured limit")

    level = _job_level(posting.title)
    if profile.seniority_levels and level:
        if level in profile.seniority_levels:
            matches.append(f"job level: {level}")
        else:
            blockers.append(f"job level is {level}")

    return ConstraintResult(
        tuple(blockers), tuple(review), tuple(matches), location_status
    )


def _arrangement(posting: JobPosting, text: str) -> str | None:
    stated = (posting.remote_status or "").casefold()
    if "hybrid" in stated or "hybrid" in text:
        return "Hybrid"
    if "remote" in stated or re.search(r"\bfully remote\b|\bremote role\b", text):
        return "Remote"
    if stated in {"onsite", "on-site", "on site"} or re.search(
        r"\bon[- ]site\b", text
    ):
        return "On-site"
    return None


def _location_status(
    posting: JobPosting, profile: CandidateProfile, arrangement: str | None
) -> str:
    if not profile.preferred_locations:
        return "unknown"
    if arrangement == "Remote":
        return "matched"
    if not posting.location:
        return "unknown"
    normalized = _normalize(posting.location)
    if any(
        _normalize(location) in normalized for location in profile.preferred_locations
    ):
        return "matched"
    posting_coordinates = resolve_location(posting.location)
    preferred_coordinates = tuple(
        coordinates
        for location in profile.preferred_locations
        if (coordinates := resolve_location(location)) is not None
    )
    if posting_coordinates is None or not preferred_coordinates:
        return "unknown"
    if any(
        distance_miles(posting_coordinates, preferred)
        <= profile.location_radius_miles
        for preferred in preferred_coordinates
    ):
        return "matched"
    return "outside"


def _required_travel(text: str) -> int | None:
    match = re.search(
        r"(?:travel|up to)\s*(\d{1,3})\s*%|(\d{1,3})\s*%\s*travel",
        text,
    )
    if not match:
        return None
    return int(match.group(1) or match.group(2))


def _job_level(title: str) -> str | None:
    value = title.casefold()
    if any(
        marker in value
        for marker in ("director", "vice president", "vp ", "head of")
    ):
        return "Executive"
    if any(
        marker in value
        for marker in ("senior", "sr.", "staff", "principal", "lead")
    ):
        return "Senior"
    if any(marker in value for marker in ("junior", "jr.", "entry", "intern")):
        return "Entry-level"
    return None


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))
