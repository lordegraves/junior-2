"""Start and health-check a loopback-only Ollama runtime for Junior."""

from __future__ import annotations

import os
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen


class OllamaRuntimeError(RuntimeError):
    """Junior could not make a local Ollama service available."""


@dataclass(frozen=True, slots=True)
class OllamaRuntimeManager:
    endpoint: str = "http://127.0.0.1:11434"
    startup_timeout_seconds: float = 15.0
    poll_interval_seconds: float = 0.2

    def ensure_running(self) -> None:
        """Return when Ollama is healthy, starting it if necessary."""

        if self._is_healthy():
            return
        with _START_LOCK:
            if self._is_healthy():
                return
            self._start_runtime()
            deadline = time.monotonic() + self.startup_timeout_seconds
            while time.monotonic() < deadline:
                if self._is_healthy():
                    return
                time.sleep(self.poll_interval_seconds)
        raise OllamaRuntimeError(
            "Junior started Ollama, but the local model service did not become ready."
        )

    def _is_healthy(self) -> bool:
        try:
            with urlopen(f"{self.endpoint}/api/tags", timeout=0.75) as response:
                return 200 <= int(response.status) < 300
        except (URLError, OSError, TimeoutError):
            return False

    def _start_runtime(self) -> None:
        executable = _find_ollama_executable()
        if executable is not None:
            environment = os.environ.copy()
            environment["OLLAMA_HOST"] = "127.0.0.1:11434"
            try:
                subprocess.Popen(
                    [str(executable), "serve"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    env=environment,
                    **_detached_process_options(),
                )
                return
            except OSError as error:
                raise OllamaRuntimeError(
                    "Junior found Ollama but could not start its local service."
                ) from error

        if (
            Path("/usr/bin/open").is_file()
            and Path("/Applications/Ollama.app").is_dir()
        ):
            try:
                subprocess.Popen(
                    ["/usr/bin/open", "-gj", "-a", "Ollama"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    start_new_session=True,
                )
                return
            except OSError as error:
                raise OllamaRuntimeError(
                    "Junior found Ollama.app but could not open it."
                ) from error

        raise OllamaRuntimeError(
            "Junior could not find Ollama. Install Ollama once; after that Junior "
            "will start the local model service automatically."
        )


def _find_ollama_executable() -> Path | None:
    discovered = shutil.which("ollama")
    local_app_data = os.environ.get("LOCALAPPDATA")
    program_files = os.environ.get("PROGRAMFILES")
    candidates = (
        Path(discovered) if discovered else None,
        Path(local_app_data) / "Programs/Ollama/ollama.exe"
        if local_app_data
        else None,
        Path(program_files) / "Ollama/ollama.exe" if program_files else None,
        Path("/opt/homebrew/bin/ollama"),
        Path("/usr/local/bin/ollama"),
        Path("/Applications/Ollama.app/Contents/Resources/ollama"),
        Path.home() / ".local/bin/ollama",
    )
    return next(
        (candidate for candidate in candidates if candidate and candidate.is_file()),
        None,
    )


def _detached_process_options() -> dict[str, int | bool]:
    if os.name == "nt":
        return {
            "creationflags": getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
            )
            | getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)
        }
    return {"start_new_session": True}


_START_LOCK = threading.Lock()
