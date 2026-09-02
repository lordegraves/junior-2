"""Launch the native Junior 2.0 desktop application."""

import sys

from junior.bootstrap import run_application


def main() -> int:
    return run_application(sys.argv)


if __name__ == "__main__":
    raise SystemExit(main())
