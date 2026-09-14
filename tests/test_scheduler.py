import plistlib
from pathlib import Path
from unittest.mock import patch

import pytest

from junior.infrastructure.scheduler import (
    SchedulerError,
    SchedulerIntegration,
    ScheduleSpec,
)


def test_schedule_spec_rejects_invalid_time_and_empty_days() -> None:
    with pytest.raises(SchedulerError, match="HH:MM"):
        ScheduleSpec(True, "breakfast", ("Mon",)).validated()
    with pytest.raises(SchedulerError, match="at least one"):
        ScheduleSpec(True, "08:00", ()).validated()


def test_macos_schedule_writes_and_loads_launch_agent(tmp_path: Path) -> None:
    scheduler = SchedulerIntegration(
        tmp_path / "data",
        platform="darwin",
        home=tmp_path,
        executable="/Applications/Junior 2.0.app/Contents/MacOS/Junior 2.0",
    )
    completed = type("Completed", (), {"returncode": 0, "stderr": ""})()

    with patch(
        "junior.infrastructure.scheduler.subprocess.run", return_value=completed
    ):
        message = scheduler.install(ScheduleSpec(True, "07:30", ("Mon", "Fri")))

    payload = plistlib.loads(scheduler._launch_agent_path.read_bytes())
    assert message == "macOS schedule installed for 07:30."
    assert payload["ProgramArguments"][-1] == "--scheduled-scan"
    assert payload["StartCalendarInterval"] == [
        {"Hour": 7, "Minute": 30, "Weekday": 2},
        {"Hour": 7, "Minute": 30, "Weekday": 6},
    ]


def test_linux_schedule_creates_user_service_and_timer(tmp_path: Path) -> None:
    scheduler = SchedulerIntegration(
        tmp_path / "data", platform="linux", home=tmp_path, executable="/opt/junior"
    )

    with patch("junior.infrastructure.scheduler.subprocess.run") as run:
        scheduler.install(ScheduleSpec(True, "18:05", ("Tue", "Thu")))

    assert "--scheduled-scan" in scheduler._systemd_service_path.read_text()
    assert "OnCalendar=Tue,Thu *-*-* 18:05:00" in (
        scheduler._systemd_timer_path.read_text()
    )
    assert run.call_count == 2


def test_remove_macos_schedule_deletes_only_junior_agent(tmp_path: Path) -> None:
    scheduler = SchedulerIntegration(
        tmp_path / "data", platform="darwin", home=tmp_path
    )
    scheduler._launch_agent_path.parent.mkdir(parents=True)
    scheduler._launch_agent_path.write_text("placeholder")

    with patch("junior.infrastructure.scheduler.subprocess.run"):
        scheduler.remove()

    assert not scheduler._launch_agent_path.exists()
