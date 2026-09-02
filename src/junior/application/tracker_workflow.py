"""Deterministic application workflow states and quick actions."""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from junior.domain.lifecycle import ApplicationRecord

TERMINAL_OUTCOMES = {"rejected", "withdrawn", "declined", "not selected", "closed"}
ACTIVE_OUTCOMES = {
    "interview scheduled",
    "interview completed",
    "waiting for feedback",
    "offer",
}


def workflow_state(application: ApplicationRecord, today: date | None = None) -> str:
    reference = today or date.today()
    status = application.status.strip().casefold()
    outcome = (application.outcome or "").strip().casefold()
    if status in TERMINAL_OUTCOMES or outcome in TERMINAL_OUTCOMES:
        return "closed"
    if status in {"interviewing", "offer"} or outcome in ACTIVE_OUTCOMES:
        return "active_pipeline"
    if status == "follow_up_due":
        return "follow_up_due"
    if status == "dormant" or outcome == "dormant":
        return "dormant"
    follow_up = _parse_date(application.follow_up_on)
    if follow_up is not None:
        return "follow_up_due" if follow_up <= reference else "follow_up_scheduled"
    if application.follow_up_on:
        return "needs_date_review"
    activity = _parse_date(application.last_activity_on) or _parse_date(
        application.applied_on
    )
    if activity is None:
        if application.last_activity_on or application.applied_on:
            return "needs_date_review"
        return "waiting"
    if activity > reference:
        return "needs_date_review"
    age = (reference - activity).days
    if age > 180:
        return "presumed_closed"
    if age > 90:
        return "stale"
    if age > 30:
        return "dormant"
    return "waiting"


def apply_quick_action(
    application: ApplicationRecord, action: str, today: date | None = None
) -> ApplicationRecord:
    reference = today or date.today()
    today_text = reference.isoformat()
    common = {"status": "applied", "last_activity_on": today_text}
    if action == "refresh_activity_today":
        return replace(application, **common)
    if action == "follow_up_next_week":
        return replace(
            application,
            **common,
            outcome="Pending / In Progress",
            follow_up_on=(reference + timedelta(days=7)).isoformat(),
        )
    if action == "follow_up_due":
        return replace(application, **common, follow_up_on=today_text)
    if action == "dormant":
        return replace(application, **common, outcome="Dormant")
    if action == "interview_scheduled":
        return replace(application, **common, outcome="Interview Scheduled")
    if action == "waiting_for_feedback":
        return replace(application, **common, outcome="Waiting For Feedback")
    raise ValueError(f"Unknown tracker quick action: {action}")


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return None
