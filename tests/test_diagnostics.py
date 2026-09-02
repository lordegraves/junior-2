import json
from pathlib import Path

from junior.infrastructure.application_database import initialize_database
from junior.infrastructure.diagnostics import run_diagnostics


class FakeResponse:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return json.dumps({"models": [{"name": "qwen2.5:3b"}]}).encode()


def test_diagnostics_validate_database_data_and_model(
    monkeypatch, tmp_path: Path
) -> None:
    database = initialize_database(tmp_path / "junior.sqlite3")
    monkeypatch.setattr(
        "junior.infrastructure.diagnostics.OllamaRuntimeManager.ensure_running",
        lambda _self: None,
    )
    monkeypatch.setattr(
        "junior.infrastructure.diagnostics.urlopen",
        lambda *_args, **_kwargs: FakeResponse(),
    )

    results = run_diagnostics(database, tmp_path)

    assert [result.name for result in results] == [
        "Database",
        "User data",
        "Local model",
    ]
    assert all(result.passed for result in results)
