"""Deterministic compensation parsing migrated from Junior 1.x."""

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class CompensationResult:
    label: str
    range_label: str
    min_usd: int | None = None
    max_usd: int | None = None


def evaluate_compensation(
    salary_text: str | None,
    compensation_floor_usd: int | None,
) -> CompensationResult:
    parsed_min, parsed_max = parse_salary_range_usd(salary_text)
    if parsed_min is None and parsed_max is None:
        return CompensationResult("Unknown", "Unknown")
    range_label = _format_range_label(parsed_min, parsed_max)
    if compensation_floor_usd is not None:
        if parsed_max is not None and parsed_max < compensation_floor_usd:
            return CompensationResult(
                "Below floor", range_label, parsed_min, parsed_max
            )
        if (
            parsed_min is not None
            and parsed_max is not None
            and parsed_min < compensation_floor_usd <= parsed_max
        ):
            return CompensationResult(
                "Partial range meets floor", range_label, parsed_min, parsed_max
            )
    return CompensationResult("Meets floor", range_label, parsed_min, parsed_max)


def parse_salary_range_usd(salary_text: str | None) -> tuple[int | None, int | None]:
    if not salary_text:
        return None, None
    normalized = salary_text.replace(",", "")
    if any(
        marker in normalized.lower()
        for marker in ("hourly", "/hr", "per hour", "an hour")
    ):
        return None, None
    values = []
    for match in re.finditer(r"(?<!\d)(\$?\d+(?:\.\d+)?\s*[kK]?)(?!\d)", normalized):
        raw = match.group(1).replace("$", "").strip()
        multiplier = 1000 if raw.lower().endswith("k") else 1
        raw = raw[:-1].strip() if multiplier == 1000 else raw
        try:
            value = int(float(raw) * multiplier)
        except ValueError:
            continue
        if value >= 10_000:
            values.append(value)
    if not values:
        return None, None
    if len(values) == 1:
        return values[0], values[0]
    return min(values), max(values)


def _format_range_label(minimum: int | None, maximum: int | None) -> str:
    if minimum is None and maximum is None:
        return "Unknown"
    if minimum == maximum and minimum is not None:
        return _format_usd(minimum)
    if minimum is None:
        return f"Up to {_format_usd(maximum)}"
    if maximum is None:
        return f"From {_format_usd(minimum)}"
    return f"{_format_usd(minimum)} - {_format_usd(maximum)}"


def _format_usd(value: int | None) -> str:
    return "Unknown" if value is None else f"${value:,.0f}"
