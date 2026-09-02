from junior.scoring.compensation import evaluate_compensation, parse_salary_range_usd


def test_parse_salary_range_usd_preserves_1x_formats() -> None:
    assert parse_salary_range_usd("$180K - $220K") == (180_000, 220_000)
    assert parse_salary_range_usd("70245.00 To 105420.00 (USD) Annually") == (
        70_245,
        105_420,
    )
    assert parse_salary_range_usd(
        "USD $126,490.00/Yr. | USD $180,700.00/Yr."
    ) == (126_490, 180_700)
    assert parse_salary_range_usd("$75/hr - $95/hr") == (None, None)


def test_evaluate_compensation_preserves_floor_classification() -> None:
    assert evaluate_compensation("$180K - $220K", 160_000).label == "Meets floor"
    assert (
        evaluate_compensation("70245 To 105420 Annually", 160_000).label
        == "Below floor"
    )
    partial = evaluate_compensation("$126,490 - $180,700", 160_000)
    assert partial.label == "Partial range meets floor"
    assert partial.range_label == "$126,490 - $180,700"


def test_evaluate_compensation_is_unknown_without_salary() -> None:
    assert evaluate_compensation(None, 160_000).label == "Unknown"
