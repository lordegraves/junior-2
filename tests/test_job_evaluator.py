from junior.domain.lifecycle import CandidateProfile, JobPosting
from junior.scoring.history_match import HistoryRecord
from junior.scoring.job_evaluator import Recommendation, evaluate_job


def _posting(salary: str, description: str) -> JobPosting:
    return JobPosting(
        "acme",
        "Acme",
        "greenhouse",
        "https://job",
        "Linux Platform Engineer",
        "Remote",
        description,
        salary_text=salary,
    )


def _profile(**changes) -> CandidateProfile:
    values = {
        "profile_id": "default",
        "name": "Candidate",
        "compensation_floor_usd": 150_000,
        "core_strengths": ("Linux", "Python", "HPC", "automation"),
    }
    values.update(changes)
    return CandidateProfile(**values)


def test_evaluator_recommends_strong_matching_job() -> None:
    result = evaluate_job(
        _posting("$160K-$190K", "Linux Python HPC automation"),
        _profile(),
        "Linux Python HPC automation",
    )
    assert result.recommendation is Recommendation.TOP_MATCH
    assert result.score == 95
    assert result.resume_match_label == "Very Strong"


def test_evaluator_omits_below_floor_and_avoid_signals() -> None:
    below = evaluate_job(
        _posting("$100K-$120K", "Linux Python HPC automation"),
        _profile(),
        "Linux Python HPC automation",
    )
    assert below.recommendation is Recommendation.OMIT
    assert below.score == 0

    avoided = evaluate_job(
        _posting("$180K", "Linux Python HPC automation on rotating shifts"),
        _profile(avoid=("rotating shifts",)),
        "Linux Python HPC automation",
    )
    assert avoided.recommendation is Recommendation.OMIT
    assert any("avoid signal" in reason for reason in avoided.reasons)


def test_evaluator_tracks_an_already_applied_role() -> None:
    history = HistoryRecord(
        "pipeline:acme", "Acme", "Linux Platform Engineer", status="Applied"
    )
    result = evaluate_job(
        _posting("$160K-$190K", "Linux Python HPC automation"),
        _profile(),
        "Linux Python HPC automation",
        (history,),
    )
    assert result.recommendation is Recommendation.TRACK_STATUS
    assert any("already_applied" in reason for reason in result.reasons)


def test_evaluator_records_approved_target_role_alignment() -> None:
    result = evaluate_job(
        _posting("$160K-$190K", "Linux Python HPC automation"),
        _profile(target_roles=("Platform Engineer",)),
        "Linux Python HPC automation",
    )

    assert result.score == 100
    assert any("Target-role alignment" in reason for reason in result.reasons)
