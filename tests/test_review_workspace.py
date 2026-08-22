from junior.application.review_fixtures import load_review_fixtures
from junior.application.review_workspace import ReviewValidationState


def test_review_fixtures_cover_primary_presentation_states() -> None:
    fixtures = load_review_fixtures()

    assert len(fixtures) == 4
    assert {fixture.fixture_id for fixture in fixtures} == {
        "fixture-alternatives",
        "fixture-required-preferred",
        "fixture-missing",
        "fixture-rejected",
    }
    assert {fixture.validation_state for fixture in fixtures} == {
        ReviewValidationState.VALIDATED,
        ReviewValidationState.REJECTED,
    }


def test_alternative_fixture_keeps_two_visible_paths() -> None:
    fixture = load_review_fixtures()[0]
    group = fixture.groups[0]

    assert len(group.paths) == 2
    assert [len(path.requirements) for path in group.paths] == [2, 2]
    assert "not connected" in fixture.engine_message.casefold()


def test_rejected_fixture_exposes_safe_reason_without_engine_result() -> None:
    fixture = next(
        item for item in load_review_fixtures() if item.fixture_id == "fixture-rejected"
    )

    assert fixture.validation_state is ReviewValidationState.REJECTED
    assert fixture.rejected_claims == (
        "evidence quote does not match the source passage",
    )
