"""Launch the native Junior 2.0 desktop application."""

import sys

from junior.bootstrap import run_application


def main() -> int:
    if "--scheduled-scan" in sys.argv:
        from junior.desktop.application import run_scheduled_scan

        return run_scheduled_scan()
    return run_application(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
