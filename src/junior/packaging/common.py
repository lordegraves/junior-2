"""Shared PyInstaller arguments for Junior desktop packages."""

from pathlib import Path


def repository_root() -> Path:
    return Path(__file__).resolve().parents[3]


def pyinstaller_arguments() -> list[str]:
    repository = repository_root()
    return [
        "--name",
        "Junior 2.0",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--icon",
        str(repository / "assets" / "Junior.png"),
        "--specpath",
        str(repository / "build"),
        "--paths",
        str(repository / "src"),
        "--collect-data",
        "junior.catalog",
        str(repository / "src" / "junior" / "__main__.py"),
    ]


def load_pyinstaller():
    try:
        import PyInstaller.__main__
    except ImportError as exc:
        raise SystemExit(
            'Install development dependencies first: pip install -e ".[dev]"'
        ) from exc
    return PyInstaller.__main__
