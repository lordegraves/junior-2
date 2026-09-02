"""Match postings to prior Junior history and classify repeat-job risk."""

from __future__ import annotations

import re
from dataclasses import dataclass

from junior.domain.lifecycle import JobPosting

_GENERIC_ROLE_TOKENS = {
    "senior",
    "sr",
    "staff",
    "principal",
    "lead",
    "engineer",
    "engineering",
    "system",
    "systems",
    "software",
    "developer",
    "role",
}
_MEANINGFUL_ROLE_TOKENS = {
    "ai",
    "cluster",
    "compute",
    "datacenter",
    "gpu",
    "hardware",
    "hpc",
    "infrastructure",
    "kubernetes",
    "linux",
    "platform",
    "reliability",
    "security",
    "site",
    "sre",
    "storage",
}


@dataclass(frozen=True, slots=True)
class HistoryRecord:
    import_key: str
    company: str
    role: str
    status: str | None = None
    outcome_category: str | None = None
    technical_match: str | None = None
    primary_blocker: str | None = None
    include_in_job_radar: bool = True


@dataclass(frozen=True, slots=True)
class HistoryRisk:
    level: str | None
    reasons: tuple[str, ...]


def summarize_history_risk(
    posting: JobPosting, records: tuple[HistoryRecord, ...]
) -> HistoryRisk:
    posting_company = _normalize(posting.company_name)
    posting_tokens = _meaningful_tokens(posting.title)
    risks: list[tuple[str, tuple[str, ...]]] = []
    for record in records:
        if not record.include_in_job_radar:
            continue
        if _normalize(record.company) != posting_company:
            continue
        record_tokens = _meaningful_tokens(record.role)
        matched = tuple(sorted(posting_tokens & record_tokens))
        if not matched:
            continue
        risks.append(
            _classify(
                record,
                allow_track_status=_strong_title_match(
                    posting.title, record.role, matched
                ),
            )
        )
    if not risks:
        return HistoryRisk(None, ())
    priority = {"neutral": 1, "caution": 2, "blocker_review": 3, "track_status": 4}
    level = max((risk[0] for risk in risks), key=lambda item: priority[item])
    reasons = tuple(dict.fromkeys(reason for _, items in risks for reason in items))
    return HistoryRisk(level, reasons)


def _classify(
    record: HistoryRecord, *, allow_track_status: bool
) -> tuple[str, tuple[str, ...]]:
    status = _clean(record.status)
    outcome = _clean(record.outcome_category)
    technical_match = _clean(record.technical_match)
    blocker = _clean(record.primary_blocker)
    if allow_track_status and (
        status.casefold() == "applied" or status.casefold().startswith("applied ")
    ):
        return "track_status", ("already_applied",)
    if outcome == "No Interview":
        reason = (
            "prior_no_interview_despite_strong_match"
            if technical_match in {"Strong", "Very Strong"}
            else "prior_no_interview"
        )
        return "caution", (reason,)
    if outcome == "Skipped / Avoid":
        if blocker != "Unknown":
            reason = _blocker_reason(blocker)
            level = (
                "caution"
                if reason.startswith("prior_risk_signal:")
                else "blocker_review"
            )
            return level, (reason,)
        return "blocker_review", ("prior_skipped_similar_role",)
    if blocker != "Unknown":
        return "caution", (_blocker_reason(blocker),)
    if status.casefold() == "rejected" or status.casefold().startswith("rejected"):
        return "caution", ("prior_rejected",)
    return "neutral", ("prior_similar_role",)


def _blocker_reason(value: str) -> str:
    token = "_".join(sorted(_tokenize(value)))
    prefix = (
        "prior_risk_signal"
        if value.casefold() == "generic remote competition"
        else "prior_blocker"
    )
    return f"{prefix}:{token}"


def _strong_title_match(posting: str, role: str, matched: tuple[str, ...]) -> bool:
    if _normalize(posting) == _normalize(role):
        return True
    if len(matched) < 2:
        return False
    posting_tokens = _meaningful_tokens(posting)
    role_tokens = _meaningful_tokens(role)
    return (
        posting_tokens == role_tokens
        or posting_tokens.issubset(role_tokens)
        or role_tokens.issubset(posting_tokens)
    )


def _meaningful_tokens(value: str) -> set[str]:
    tokens = _tokenize(value) - _GENERIC_ROLE_TOKENS
    return tokens & _MEANINGFUL_ROLE_TOKENS or tokens


def _tokenize(value: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", value.casefold()))


def _normalize(value: str) -> str:
    return " ".join(sorted(_tokenize(value)))


def _clean(value: str | None) -> str:
    return value.strip() if value and value.strip() else "Unknown"
