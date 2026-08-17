from junior.catalog.models import CompanyCatalogEntry, build_effective_catalog
from junior.catalog.starter_catalog import load_starter_catalog


def test_starter_catalog_matches_the_junior_1x_catalog() -> None:
    catalog = load_starter_catalog()

    assert catalog.catalog_version == 1
    assert len(catalog.companies) == 50
    assert {company.company_id for company in catalog.companies} >= {
        "starter_affirm",
        "starter_cloudflare",
        "starter_google",
        "starter_microsoft",
        "starter_walmart",
        "starter_ford",
    }
    assert {company.source_type for company in catalog.companies} == {
        "greenhouse",
        "google_careers",
        "eightfold",
        "walmart",
        "talentbrew",
    }


def test_starter_catalog_contains_no_user_state_or_secret_fields() -> None:
    catalog = load_starter_catalog()
    forbidden_terms = {
        "enabled",
        "profile_id",
        "selected",
        "api_key",
        "password",
        "secret",
        "token",
    }

    for company in catalog.companies:
        setting_names = {str(key).casefold() for key in company.source_settings}
        assert forbidden_terms.isdisjoint(setting_names)


def test_user_entry_overrides_effective_view_without_changing_shipped_data() -> None:
    starter = load_starter_catalog()
    original = next(
        company
        for company in starter.companies
        if company.company_id == "starter_affirm"
    )
    local_override = CompanyCatalogEntry(
        company_id=original.company_id,
        name="Affirm (local name)",
        source_type=original.source_type,
        source_identifier=original.source_identifier,
        careers_url=original.careers_url,
        source_settings=original.source_settings,
    )

    effective = build_effective_catalog(starter, (local_override,))

    effective_affirm = next(
        company for company in effective if company.company_id == original.company_id
    )
    assert effective_affirm.name == "Affirm (local name)"
    assert original.name == "Affirm"
