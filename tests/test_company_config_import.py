from pathlib import Path

import pytest

from junior.infrastructure.application_database import (
    get_company,
    initialize_database,
    list_companies,
)
from junior.infrastructure.company_config_import import import_company_config


def test_import_preserves_source_specific_company_settings(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    source = tmp_path / "companies.yaml"
    source.write_text(
        """companies:
  - company_key: hpe
    name: HPE
    source_type: workday
    source_url: https://hpe.example/jobs
    source_base_url: https://hpe.example/careers
    page_size: 20
    enabled: true
    notes: Existing target
  - company_key: openai
    name: OpenAI
    source_type: ashby
    source_slug: openai
    enabled: false
""",
        encoding="utf-8",
    )

    count = import_company_config(source, database)

    assert count == 2
    assert len(list_companies(database)) == 2
    hpe = get_company(database, "hpe")
    assert hpe is not None
    assert hpe["source_settings"] == {
        "page_size": 20,
        "source_base_url": "https://hpe.example/careers",
    }
    assert hpe["notes"] == "Existing target"


def test_import_rejects_non_company_yaml(tmp_path: Path) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    source = tmp_path / "settings.yaml"
    source.write_text("database_path: junior.sqlite3\n", encoding="utf-8")

    with pytest.raises(ValueError, match="companies list"):
        import_company_config(source, database)
