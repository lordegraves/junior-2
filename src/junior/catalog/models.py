"""Stable catalog records shared by shipped data and user-owned additions."""

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Any


@dataclass(frozen=True, slots=True)
class CompanyCatalogEntry:
    company_id: str
    name: str
    source_type: str
    source_identifier: str
    careers_url: str
    source_settings: Mapping[str, Any]

    def __post_init__(self) -> None:
        required = {
            "company_id": self.company_id,
            "name": self.name,
            "source_type": self.source_type,
            "source_identifier": self.source_identifier,
            "careers_url": self.careers_url,
        }
        for field_name, value in required.items():
            if not value.strip():
                raise ValueError(f"{field_name} is required")
        if not self.careers_url.startswith("https://"):
            raise ValueError("careers_url must use HTTPS")
        object.__setattr__(
            self,
            "source_settings",
            MappingProxyType(dict(self.source_settings)),
        )


@dataclass(frozen=True, slots=True)
class StarterCompanyCatalog:
    catalog_version: int
    companies: tuple[CompanyCatalogEntry, ...]

    def __post_init__(self) -> None:
        if self.catalog_version < 1:
            raise ValueError("catalog_version must be positive")
        company_ids = [company.company_id for company in self.companies]
        if len(company_ids) != len(set(company_ids)):
            raise ValueError("starter catalog contains duplicate company identifiers")


def build_effective_catalog(
    starter: StarterCompanyCatalog,
    user_entries: tuple[CompanyCatalogEntry, ...],
) -> tuple[CompanyCatalogEntry, ...]:
    """Layer local choices over shipped defaults without changing shipped data."""

    effective = {company.company_id: company for company in starter.companies}
    effective.update({company.company_id: company for company in user_entries})
    return tuple(
        sorted(effective.values(), key=lambda company: company.name.casefold())
    )
