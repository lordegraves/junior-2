"""Self-contained health checks for an installed Junior application."""

from __future__ import annotations

import json
import os
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

from junior.infrastructure.ollama_runtime import OllamaRuntimeManager


@dataclass(frozen=True, slots=True)
class DiagnosticResult:
    name: str
    passed: bool
    detail: str


def run_diagnostics(
    database_path: str | Path,
    data_directory: str | Path,
    *,
    model_id: str = "qwen2.5:3b",
    endpoint: str = "http://127.0.0.1:11434",
) -> tuple[DiagnosticResult, ...]:
    return (
        _database_check(Path(database_path)),
        _data_directory_check(Path(data_directory)),
        _model_check(model_id, endpoint),
    )


def _database_check(path: Path) -> DiagnosticResult:
    try:
        with sqlite3.connect(path) as connection:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            version = connection.execute(
                "SELECT value FROM schema_metadata WHERE key = 'schema_version'"
            ).fetchone()[0]
    except (OSError, sqlite3.Error, TypeError) as error:
        return DiagnosticResult("Database", False, str(error))
    passed = integrity == "ok"
    return DiagnosticResult(
        "Database", passed, f"integrity={integrity}; schema={version}"
    )


def _data_directory_check(path: Path) -> DiagnosticResult:
    passed = path.is_dir() and os.access(path, os.R_OK | os.W_OK)
    detail = str(path) if passed else f"Not readable and writable: {path}"
    return DiagnosticResult("User data", passed, detail)


def _model_check(model_id: str, endpoint: str) -> DiagnosticResult:
    try:
        OllamaRuntimeManager(endpoint=endpoint).ensure_running()
        with urlopen(f"{endpoint.rstrip('/')}/api/tags", timeout=5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        names = {
            str(item.get("name") or item.get("model") or "")
            for item in payload.get("models", [])
            if isinstance(item, dict)
        }
    except Exception as error:
        return DiagnosticResult("Local model", False, str(error))
    passed = model_id in names
    detail = f"{model_id} is installed" if passed else f"Missing model: {model_id}"
    return DiagnosticResult("Local model", passed, detail)
