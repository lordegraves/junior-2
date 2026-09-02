"""User-facing action taxonomy retained from Junior 1.x."""

from __future__ import annotations

from dataclasses import dataclass

from junior.domain.lifecycle import JobPosting

HIGH_COMPETITION = {
    "openai",
    "anthropic",
    "nvidia",
    "meta",
    "google",
    "microsoft",
    "apple",
    "netflix",
    "databricks",
}
ROLE_MISMATCH = {
    "frontend",
    "full stack",
    "product manager",
    "program manager",
    "project manager",
    "account manager",
    "business development",
    "developer advocate",
    "compliance",
    "facilities",
    "sourcing",
    "engineering manager",
    "technical program manager",
    "director",
    "sales engineer",
    "customer success",
    "incident manager",
    "field services manager",
}


@dataclass(frozen=True, slots=True)
class ActionResult:
    action: str
    hiring_probability: str
    risks: tuple[str, ...]


def recommend_action(
    posting: JobPosting,
    *,
    recommendation: str,
    resume_match: str,
    history_level: str | None,
    history_reasons: tuple[str, ...],
    compensation_label: str,
) -> ActionResult:
    risks = _risks(posting, resume_match, history_level, compensation_label)
    if recommendation == "track_status" or "already_applied" in history_reasons:
        return ActionResult("track_status", "Tracked", risks)
    if history_level == "blocker_review":
        return ActionResult("previously_reviewed", "Low", risks)
    if recommendation == "omit":
        return ActionResult("pass", "Very Low", risks)
    probability = _probability(resume_match, risks)
    if recommendation == "top_match":
        if "high_competition_employer" in risks or history_level == "caution":
            return ActionResult("apply_with_recruiter", probability, risks)
        return ActionResult("apply", probability, risks)
    if resume_match in {"Very Strong", "Strong"}:
        if "high_competition_employer" in risks or "role_family_mismatch" in risks:
            return ActionResult("network_first", probability, risks)
        return ActionResult("tailor_resume", probability, risks)
    return ActionResult("hold", probability, risks)


def _risks(
    posting: JobPosting,
    resume_match: str,
    history_level: str | None,
    compensation_label: str,
) -> tuple[str, ...]:
    company = posting.company_name.casefold()
    title = posting.title.casefold()
    risks: list[str] = []
    if any(item in company for item in HIGH_COMPETITION):
        risks.append("high_competition_employer")
    if any(item in title for item in ROLE_MISMATCH):
        risks.append("role_family_mismatch")
    if compensation_label == "Below floor":
        risks.append("below_compensation_floor")
    if resume_match == "Weak":
        risks.append("weak_resume_match")
    if history_level in {"caution", "blocker_review"}:
        risks.append(f"history_{history_level}")
    return tuple(risks)


def _probability(resume_match: str, risks: tuple[str, ...]) -> str:
    if "role_family_mismatch" in risks or "weak_resume_match" in risks:
        return "Low"
    if resume_match == "Very Strong" and not risks:
        return "High"
    if resume_match in {"Very Strong", "Strong", "Medium"}:
        return "Medium"
    return "Very Low"
