from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import URLError

import pytest

from junior.infrastructure.ollama_runtime import (
    OllamaRuntimeError,
    OllamaRuntimeManager,
)


class _HealthyResponse:
    status = 200

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def test_running_service_is_not_started_again() -> None:
    manager = OllamaRuntimeManager()
    with (
        patch(
            "junior.infrastructure.ollama_runtime.urlopen",
            return_value=_HealthyResponse(),
        ),
        patch.object(OllamaRuntimeManager, "_start_runtime") as start,
    ):
        manager.ensure_running()

    start.assert_not_called()


def test_stopped_service_is_started_and_waited_for() -> None:
    manager = OllamaRuntimeManager(startup_timeout_seconds=1, poll_interval_seconds=0)
    with (
        patch(
            "junior.infrastructure.ollama_runtime.urlopen",
            side_effect=[URLError("stopped"), URLError("stopped"), _HealthyResponse()],
        ),
        patch.object(OllamaRuntimeManager, "_start_runtime") as start,
    ):
        manager.ensure_running()

    start.assert_called_once_with()


def test_cli_runtime_starts_detached_loopback_service() -> None:
    manager = OllamaRuntimeManager()
    process = Mock()
    with (
        patch(
            "junior.infrastructure.ollama_runtime._find_ollama_executable",
            return_value=Path("/opt/homebrew/bin/ollama"),
        ),
        patch(
            "junior.infrastructure.ollama_runtime.subprocess.Popen",
            return_value=process,
        ) as popen,
    ):
        manager._start_runtime()

    assert popen.call_args.args[0] == ["/opt/homebrew/bin/ollama", "serve"]
    assert popen.call_args.kwargs["env"]["OLLAMA_HOST"] == "127.0.0.1:11434"
    assert popen.call_args.kwargs["start_new_session"] is True


def test_windows_runtime_uses_no_console_window() -> None:
    with patch("junior.infrastructure.ollama_runtime.os.name", "nt"):
        from junior.infrastructure.ollama_runtime import _detached_process_options

        process_options = _detached_process_options()

    assert "creationflags" in process_options
    assert "start_new_session" not in process_options


def test_windows_standard_install_location_is_discovered(tmp_path: Path) -> None:
    executable = tmp_path / "Programs" / "Ollama" / "ollama.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    with (
        patch("junior.infrastructure.ollama_runtime.shutil.which", return_value=None),
        patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}, clear=False),
    ):
        from junior.infrastructure.ollama_runtime import _find_ollama_executable

        assert _find_ollama_executable() == executable


def test_missing_runtime_has_actionable_error() -> None:
    manager = OllamaRuntimeManager()
    with (
        patch(
            "junior.infrastructure.ollama_runtime._find_ollama_executable",
            return_value=None,
        ),
        patch("junior.infrastructure.ollama_runtime.Path.is_file", return_value=False),
    ):
        with pytest.raises(OllamaRuntimeError, match="Install Ollama once"):
            manager._start_runtime()
