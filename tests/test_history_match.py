from junior.domain.lifecycle import JobPosting
from junior.scoring.history_match import HistoryRecord, summarize_history_risk


def _posting(title: str = "Senior Infrastructure Engineer") -> JobPosting:
    return JobPosting("example", "Example AI", "stub", "https://job", title)


def _record(**changes) -> HistoryRecord:
    values = {
        "import_key": "pipeline:example",
        "company": "Example AI",
        "role": "Senior Infrastructure Engineer",
        "status": "Rejected - No Interview",
        "outcome_category": "No Interview",
        "technical_match": "Very Strong",
    }
    values.update(changes)
    return HistoryRecord(**values)


def test_prior_no_interview_is_a_caution() -> None:
    risk = summarize_history_risk(_posting(), (_record(),))
    assert risk.level == "caution"
    assert risk.reasons == ("prior_no_interview_despite_strong_match",)


def test_strong_applied_title_tracks_status() -> None:
    risk = summarize_history_risk(
        _posting("Site Reliability Engineer"),
        (
            _record(
                role="Senior Site Reliability Engineer",
                status="Applied",
                outcome_category=None,
            ),
        ),
    )
    assert risk.level == "track_status"
    assert risk.reasons == ("already_applied",)


def test_weak_applied_title_does_not_track_status() -> None:
    risk = summarize_history_risk(
        _posting(),
        (
            _record(
                role="Infrastructure Operations Engineer",
                status="Applied",
                outcome_category=None,
            ),
        ),
    )
    assert risk.level == "neutral"


def test_prior_skipped_blocker_requires_review() -> None:
    risk = summarize_history_risk(
        _posting(),
        (
            _record(
                outcome_category="Skipped / Avoid",
                primary_blocker="Production Kubernetes",
            ),
        ),
    )
    assert risk.level == "blocker_review"
    assert risk.reasons == ("prior_blocker:kubernetes_production",)
