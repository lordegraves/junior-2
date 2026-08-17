"""Development entry point for the Junior 2.0 skeleton."""

from junior.bootstrap import describe_runtime


def main() -> int:
    """Report the currently wired capability without pretending it is a product."""
    print(describe_runtime())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
