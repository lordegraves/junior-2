"""Import Junior 1.x company YAML into Junior 2.0's private database."""

from __future__ import annotations

from pathlib import Path

import yaml

from junior.infrastructure.application_database import save_company

_CORE_KEYS = {
    "company_key",
    "name",
    "source_type",
    "source_slug",
    "source_url",
    "enabled",
    "notes",
}


def import_company_config(
    source_path: str | Path, database_path: str | Path
) -> int:
    path = Path(source_path).expanduser().resolve()
    if not path.is_file():
        raise ValueError("Select an existing Junior company YAML file.")
    try:
        payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ValueError("Junior could not parse that company YAML file.") from error
    if not isinstance(payload, dict) or not isinstance(payload.get("companies"), list):
        raise ValueError("Company YAML must contain a top-level companies list.")

    imported = 0
    for index, raw_company in enumerate(payload["companies"], start=1):
        if not isinstance(raw_company, dict):
            raise ValueError(f"Company entry {index} must be a mapping.")
        settings = {
            str(key): value
            for key, value in raw_company.items()
            if key not in _CORE_KEYS
        }
        try:
            save_company(
                database_path,
                company_key=str(raw_company.get("company_key") or ""),
                name=str(raw_company.get("name") or ""),
                source_type=str(raw_company.get("source_type") or ""),
                source_slug=_optional_string(raw_company.get("source_slug")),
                source_url=_optional_string(raw_company.get("source_url")),
                enabled=bool(raw_company.get("enabled", True)),
                source_settings=settings,
                notes=_optional_string(raw_company.get("notes")),
            )
        except ValueError as error:
            raise ValueError(f"Invalid company entry {index}: {error}") from error
        imported += 1
    return imported


def _optional_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
