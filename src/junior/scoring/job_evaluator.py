"""Deterministic, auditable posting evaluation for production scans."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from junior.domain.lifecycle import CandidateProfile, JobPosting
from junior.scoring.compensation import evaluate_compensation
from junior.scoring.history_match import HistoryRecord, summarize_history_risk
from junior.scoring.legacy_policy import evaluate_legacy_policy
from junior.scoring.recommendation_actions import recommend_action
from junior.scoring.resume_match import match_resume_to_posting


class Recommendation(StrEnum):
    TOP_MATCH = "top_match"
    REVIEW_NEEDED = "review_needed"
    OMIT = "omit"
    TRACK_STATUS = "track_status"


@dataclass(frozen=True, slots=True)
class JobEvaluation:
    score: int
    recommendation: Recommendation
    compensation_label: str
    compensation_range: str
    resume_match_label: str
    evidence: tuple[str, ...]
    gaps: tuple[str, ...]
    reasons: tuple[str, ...]
    policy_score: int = 0
    location_status: str = "unknown"
    recommended_action: str = "hold"
    hiring_probability: str = "Unknown"
    risk_flags: tuple[str, ...] = ()


def evaluate_job(
    posting: JobPosting,
    profile: CandidateProfile | None,
    resume_text: str | None,
    history_records: tuple[HistoryRecord, ...] = (),
) -> JobEvaluation:
    floor = profile.compensation_floor_usd if profile else None
    compensation = evaluate_compensation(posting.salary_text, floor)
    match = match_resume_to_posting(posting, profile, resume_text)
    policy = evaluate_legacy_policy(posting)
    reasons: list[str] = []
    reasons.extend(f"Legacy policy: {reason}." for reason in policy.reasons)
    score = {
        "Very Strong": 85,
        "Strong": 72,
        "Medium": 50,
        "Weak": 20,
        "Unknown": 35,
    }[match.label]
    if compensation.label == "Meets floor":
        score += 10
        reasons.append("The published compensation meets the profile floor.")
    elif compensation.label == "Partial range meets floor":
        score += 3
        reasons.append("Only part of the published range meets the profile floor.")
    elif compensation.label == "Below floor":
        score = 0
        reasons.append("The published compensation is below the profile floor.")
    else:
        reasons.append("Published compensation could not be resolved.")
    if match.evidence:
        reasons.append(f"Matched profile evidence: {', '.join(match.evidence)}.")
    if match.gaps:
        score -= min(30, len(match.gaps) * 10)
        reasons.append(f"Known gaps: {', '.join(match.gaps)}.")
    avoided = _matching_terms(posting, profile.avoid if profile else ())
    if avoided:
        score = 0
        reasons.append(f"Profile avoid signal: {', '.join(avoided)}.")
    history_risk = summarize_history_risk(posting, history_records)
    reasons.extend(f"History risk: {reason}." for reason in history_risk.reasons)
    if history_risk.level == "blocker_review":
        score -= 15
    elif history_risk.level == "caution":
        score -= 5
    score = max(0, min(100, score))
    if history_risk.level == "track_status":
        recommendation = Recommendation.TRACK_STATUS
    elif (
        compensation.label == "Below floor"
        or avoided
        or score < 35
        or policy.location_status == "skipped"
        or any(
            reason.startswith("excluded_title_keyword:") for reason in policy.reasons
        )
    ):
        recommendation = Recommendation.OMIT
    elif (
        score >= 70
        and not match.gaps
        and history_risk.level != "blocker_review"
        and "production_kubernetes_primary_risk" not in policy.reasons
    ):
        recommendation = Recommendation.TOP_MATCH
    else:
        recommendation = Recommendation.REVIEW_NEEDED
    action = recommend_action(
        posting,
        recommendation=recommendation.value,
        resume_match=match.label,
        history_level=history_risk.level,
        history_reasons=history_risk.reasons,
        compensation_label=compensation.label,
    )
    return JobEvaluation(
        score,
        recommendation,
        compensation.label,
        compensation.range_label,
        match.label,
        match.evidence,
        match.gaps,
        tuple(reasons),
        policy.score,
        policy.location_status,
        action.action,
        action.hiring_probability,
        action.risks,
    )


def _matching_terms(posting: JobPosting, terms: tuple[str, ...]) -> tuple[str, ...]:
    text = " ".join(
        filter(None, (posting.title, posting.location, posting.description))
    ).casefold()
    return tuple(term for term in dict.fromkeys(terms) if term.casefold() in text)
