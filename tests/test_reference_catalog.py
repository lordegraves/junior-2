from junior.infrastructure.reference_catalog import (
    distance_miles,
    resolve_location,
    suggest_locations,
    suggest_occupations,
)


def test_packaged_occupation_catalog_searches_official_and_alternate_titles() -> None:
    matches = suggest_occupations("platform engineer")

    assert matches
    assert matches[0]["label"] == "Platform Engineer"
    assert matches[0]["value"] == "15-1299.08"


def test_packaged_location_catalog_resolves_city_state_and_zip() -> None:
    matches = suggest_locations("Fort Collins")

    assert matches[0]["label"] == "Fort Collins, CO"
    assert resolve_location("Fort Collins, Colorado") == (
        matches[0]["latitude"],
        matches[0]["longitude"],
    )
    assert resolve_location("ZIP 80525") is not None


def test_location_distance_uses_geographic_coordinates() -> None:
    fort_collins = resolve_location("Fort Collins, CO")
    cheyenne = resolve_location("Cheyenne, WY")

    assert fort_collins is not None and cheyenne is not None
    assert 40 < distance_miles(fort_collins, cheyenne) < 45
