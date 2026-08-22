"""Composition root where Junior's concrete adapters are selected."""

from collections.abc import Sequence


def run_application(arguments: Sequence[str] | None = None) -> int:
    """Launch the current native review workspace."""

    from junior.desktop.application import run_desktop_application

    return run_desktop_application(arguments)
