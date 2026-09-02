from datetime import date

import pytest

from junior.application.tracker_workflow import apply_quick_action, workflow_state
from junior.domain.lifecycle import ApplicationRecord


def record(**changes) -> ApplicationRecord:
    values = dict(
        job_radar_id="jr-1",
        company_name="Example",
        role_title="Engineer",
        source_url=None,
        status="applied",
        follow_up_on=None,
        outcome=None,
        notes=None,
        applied_on=None,
        last_activity_on=None,
    )
    values.update(changes)
    return ApplicationRecord(**values)


@pytest.mark.parametrize(
    ("changes", "expected"),
    [
        ({"follow_up_on": "2026-09-02"}, "follow_up_due"),
        ({"follow_up_on": "2026-09-09"}, "follow_up_scheduled"),
        ({"follow_up_on": "bad"}, "needs_date_review"),
        ({"outcome": "Interview Scheduled"}, "active_pipeline"),
        ({"status": "rejected"}, "closed"),
        ({"last_activity_on": "2026-05-01"}, "stale"),
        ({"last_activity_on": "2026-01-01"}, "presumed_closed"),
        ({}, "waiting"),
    ],
)
def test_workflow_state(changes, expected):
    assert workflow_state(record(**changes), date(2026, 9, 2)) == expected


def test_quick_action_schedules_follow_up():
    updated = apply_quick_action(record(), "follow_up_next_week", date(2026, 9, 2))
    assert updated.follow_up_on == "2026-09-09"
    assert updated.last_activity_on == "2026-09-02"
    assert updated.outcome == "Pending / In Progress"


def test_unknown_quick_action_is_rejected():
    with pytest.raises(ValueError, match="Unknown tracker quick action"):
        apply_quick_action(record(), "invented")
