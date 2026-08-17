"""Load and validate the versioned starter company catalog shipped with Junior."""

import json
from importlib.resources import files
from typing import Any

from junior.catalog.models import CompanyCatalogEntry, StarterCompanyCatalog

_CATALOG_RESOURCE = "starter_catalog_v1.json"
_SECRET_FIELD_TERMS = {"api_key", "password", "secret", "token"}


def load_starter_catalog() -> StarterCompanyCatalog:
    resource = files("junior.catalog").joinpath(_CATALOG_RESOURCE)
    raw = json.loads(resource.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("starter catalog must be a JSON object")
    version = raw.get("catalog_version")
    companies = raw.get("companies")
    if not isinstance(version, int) or not isinstance(companies, list):
        raise ValueError("starter catalog version or companies are invalid")
    entries = tuple(_parse_entry(company) for company in companies)
    return StarterCompanyCatalog(version, entries)


def _parse_entry(raw: Any) -> CompanyCatalogEntry:
    if not isinstance(raw, dict):
        raise ValueError("starter catalog company must be an object")
    source_settings = raw.get("source_settings")
    if not isinstance(source_settings, dict):
        raise ValueError("starter catalog source_settings must be an object")
    unsafe_fields = {
        str(key)
        for key in source_settings
        if any(term in str(key).casefold() for term in _SECRET_FIELD_TERMS)
    }
    if unsafe_fields:
        names = ", ".join(sorted(unsafe_fields))
        raise ValueError(f"starter catalog cannot contain secret fields: {names}")
    return CompanyCatalogEntry(
        company_id=str(raw.get("company_id") or ""),
        name=str(raw.get("name") or ""),
        source_type=str(raw.get("source_type") or ""),
        source_identifier=str(raw.get("source_identifier") or ""),
        careers_url=str(raw.get("careers_url") or ""),
        source_settings=source_settings,
    )
