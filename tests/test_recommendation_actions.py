from junior.domain.lifecycle import JobPosting
from junior.scoring.recommendation_actions import recommend_action


def _posting(company="Acme", title="Linux Infrastructure Engineer"):
    return JobPosting("acme", company, "stub", "https://job", title)


def test_action_taxonomy_covers_apply_track_and_pass() -> None:
    apply = recommend_action(
        _posting(),
        recommendation="top_match",
        resume_match="Very Strong",
        history_level=None,
        history_reasons=(),
        compensation_label="Meets floor",
    )
    assert (apply.action, apply.hiring_probability) == ("apply", "High")
    tracked = recommend_action(
        _posting(),
        recommendation="track_status",
        resume_match="Strong",
        history_level="track_status",
        history_reasons=("already_applied",),
        compensation_label="Unknown",
    )
    assert tracked.action == "track_status"
    passed = recommend_action(
        _posting(),
        recommendation="omit",
        resume_match="Weak",
        history_level=None,
        history_reasons=(),
        compensation_label="Below floor",
    )
    assert passed.action == "pass"


def test_high_competition_top_match_uses_recruiter() -> None:
    result = recommend_action(
        _posting(company="NVIDIA"),
        recommendation="top_match",
        resume_match="Very Strong",
        history_level=None,
        history_reasons=(),
        compensation_label="Meets floor",
    )
    assert result.action == "apply_with_recruiter"
    assert "high_competition_employer" in result.risks
