"""Install Junior's user-level scheduled scan on supported desktop platforms."""

from __future__ import annotations

import os
import plistlib
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path


class SchedulerError(RuntimeError):
    """A scheduler operation could not be completed safely."""


@dataclass(frozen=True, slots=True)
class ScheduleSpec:
    enabled: bool
    local_time: str
    weekdays: tuple[str, ...]

    def validated(self) -> ScheduleSpec:
        try:
            hour_text, minute_text = self.local_time.strip().split(":", 1)
            hour, minute = int(hour_text), int(minute_text)
        except (ValueError, TypeError) as error:
            raise SchedulerError("Enter the local scan time as HH:MM.") from error
        if not 0 <= hour <= 23 or not 0 <= minute <= 59:
            raise SchedulerError("Enter a valid local scan time as HH:MM.")
        if self.enabled and not self.weekdays:
            raise SchedulerError("Select at least one scan day.")
        unknown = set(self.weekdays) - set(WEEKDAY_NUMBERS)
        if unknown:
            raise SchedulerError("The scan schedule contains an unknown weekday.")
        return ScheduleSpec(self.enabled, f"{hour:02d}:{minute:02d}", self.weekdays)


WEEKDAY_NUMBERS = {
    "Mon": 1,
    "Tue": 2,
    "Wed": 3,
    "Thu": 4,
    "Fri": 5,
    "Sat": 6,
    "Sun": 0,
}


class SchedulerIntegration:
    """Manage one user-owned scheduler definition without administrator access."""

    def __init__(
        self,
        data_directory: str | Path,
        *,
        platform: str | None = None,
        home: str | Path | None = None,
        executable: str | Path | None = None,
    ) -> None:
        self.data_directory = Path(data_directory)
        self.platform = platform or sys.platform
        self.home = Path(home) if home is not None else Path.home()
        self.executable = Path(executable) if executable else Path(sys.executable)

    def install(self, spec: ScheduleSpec) -> str:
        spec = spec.validated()
        if self.platform == "darwin":
            return self._install_launch_agent(spec)
        if self.platform.startswith("linux"):
            return self._install_systemd_timer(spec)
        if self.platform.startswith("win"):
            return self._install_windows_task(spec)
        raise SchedulerError(f"Scheduling is not supported on {self.platform}.")

    def remove(self) -> str:
        if self.platform == "darwin":
            path = self._launch_agent_path
            subprocess.run(
                ["launchctl", "bootout", f"gui/{os.getuid()}", str(path)],
                check=False,
                capture_output=True,
            )
            path.unlink(missing_ok=True)
            return "The macOS scheduled scan was removed."
        if self.platform.startswith("linux"):
            subprocess.run(
                ["systemctl", "--user", "disable", "--now", "junior-2.timer"],
                check=False,
                capture_output=True,
            )
            self._systemd_service_path.unlink(missing_ok=True)
            self._systemd_timer_path.unlink(missing_ok=True)
            subprocess.run(
                ["systemctl", "--user", "daemon-reload"], check=False
            )
            return "The Linux scheduled scan was removed."
        if self.platform.startswith("win"):
            subprocess.run(
                ["schtasks", "/Delete", "/TN", "Junior 2.0 Scan", "/F"],
                check=False,
                capture_output=True,
            )
            return "The Windows scheduled scan was removed."
        raise SchedulerError(f"Scheduling is not supported on {self.platform}.")

    @property
    def _command(self) -> list[str]:
        return [str(self.executable), "--scheduled-scan"]

    @property
    def _launch_agent_path(self) -> Path:
        return self.home / "Library/LaunchAgents/com.junior.app.scan.plist"

    def _install_launch_agent(self, spec: ScheduleSpec) -> str:
        hour, minute = (int(value) for value in spec.local_time.split(":"))
        calendar = [
            {"Hour": hour, "Minute": minute, "Weekday": WEEKDAY_NUMBERS[day] + 1}
            for day in spec.weekdays
        ]
        path = self._launch_agent_path
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "Label": "com.junior.app.scan",
            "ProgramArguments": self._command,
            "StartCalendarInterval": calendar,
            "RunAtLoad": False,
            "StandardOutPath": str(self.data_directory / "scheduled-scan.log"),
            "StandardErrorPath": str(self.data_directory / "scheduled-scan-error.log"),
        }
        path.write_bytes(plistlib.dumps(payload, sort_keys=True))
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}", str(path)],
            check=False,
            capture_output=True,
        )
        if spec.enabled:
            result = subprocess.run(
                ["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)],
                check=False,
                capture_output=True,
                text=True,
            )
            if result.returncode:
                raise SchedulerError(result.stderr.strip() or "launchctl failed.")
        return f"macOS schedule installed for {spec.local_time}."

    @property
    def _systemd_directory(self) -> Path:
        return self.home / ".config/systemd/user"

    @property
    def _systemd_service_path(self) -> Path:
        return self._systemd_directory / "junior-2.service"

    @property
    def _systemd_timer_path(self) -> Path:
        return self._systemd_directory / "junior-2.timer"

    def _install_systemd_timer(self, spec: ScheduleSpec) -> str:
        self._systemd_directory.mkdir(parents=True, exist_ok=True)
        self._systemd_service_path.write_text(
            "[Unit]\nDescription=Junior 2.0 scheduled scan\n\n"
            "[Service]\nType=oneshot\nExecStart=" + " ".join(self._command) + "\n",
            encoding="utf-8",
        )
        days = ",".join(spec.weekdays)
        self._systemd_timer_path.write_text(
            "[Unit]\nDescription=Junior 2.0 scheduled scan\n\n"
            f"[Timer]\nOnCalendar={days} *-*-* {spec.local_time}:00\n"
            "Persistent=true\n\n"
            "[Install]\nWantedBy=timers.target\n",
            encoding="utf-8",
        )
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        action = "enable" if spec.enabled else "disable"
        subprocess.run(
            ["systemctl", "--user", action, "--now", "junior-2.timer"],
            check=True,
        )
        return f"Linux schedule installed for {spec.local_time}."

    def _install_windows_task(self, spec: ScheduleSpec) -> str:
        days = ",".join(day.upper() for day in spec.weekdays)
        command = subprocess.list2cmdline(self._command)
        args = [
            "schtasks", "/Create", "/TN", "Junior 2.0 Scan", "/TR", command,
            "/SC", "WEEKLY", "/D", days, "/ST", spec.local_time, "/F",
        ]
        if not spec.enabled:
            args.extend(("/DISABLE",))
        result = subprocess.run(args, check=False, capture_output=True, text=True)
        if result.returncode:
            raise SchedulerError(result.stderr.strip() or result.stdout.strip())
        return f"Windows schedule installed for {spec.local_time}."
