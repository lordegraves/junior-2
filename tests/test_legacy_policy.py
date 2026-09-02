from junior.domain.lifecycle import JobPosting
from junior.scoring.legacy_policy import classify_location, evaluate_legacy_policy


def _posting(title: str, location: str, body: str = "") -> JobPosting:
    return JobPosting("acme", "Acme", "stub", "https://job", title, location, body)


def test_legacy_policy_weights_title_more_than_body() -> None:
    result = evaluate_legacy_policy(
        _posting("Senior Linux Infrastructure Engineer", "Remote", "Python")
    )
    assert result.score == 64
    assert "+30 title:linux" in result.reasons
    assert "+30 title:infrastructure" in result.reasons
    assert "+4 body:python" in result.reasons


def test_legacy_policy_blocks_skipped_location_and_excluded_title() -> None:
    result = evaluate_legacy_policy(
        _posting("Infrastructure Customer Success Engineer", "London, UK")
    )
    assert result.location_status == "skipped"
    assert not result.top_match_eligible
    assert "excluded_title_keyword:customer success" in result.reasons


def test_legacy_location_preserves_limited_travel_rule() -> None:
    assert classify_location("remote - travel required 10-20%") == "allowed_with_travel"
    assert classify_location("remote - travel required") == "mixed"


def test_production_kubernetes_primary_role_is_not_top_match() -> None:
    result = evaluate_legacy_policy(
        _posting(
            "Senior Kubernetes Infrastructure SRE",
            "Remote",
            "Own production Kubernetes clusters and control plane reliability.",
        )
    )
    assert not result.top_match_eligible
    assert "production_kubernetes_primary_risk" in result.reasons


def test_kubernetes_with_hpc_counterevidence_can_remain_top_match() -> None:
    result = evaluate_legacy_policy(
        _posting(
            "Senior Kubernetes Infrastructure SRE",
            "Remote",
            "Operate Kubernetes clusters for HPC, Slurm, GPU, and bare metal systems.",
        )
    )
    assert result.top_match_eligible
