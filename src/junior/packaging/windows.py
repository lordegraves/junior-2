"""Build Junior as a native Windows Inno Setup installer."""

import subprocess

from junior.packaging.common import (
    load_pyinstaller,
    pyinstaller_arguments,
    repository_root,
)


def main() -> int:
    pyinstaller = load_pyinstaller()
    repository = repository_root()
    pyinstaller.run(pyinstaller_arguments())
    subprocess.run(
        [
            "ISCC.exe",
            f"/DSourceRoot={repository}",
            str(repository / "assets" / "Junior2.iss"),
        ],
        check=True,
    )
    installer = repository / "dist" / "Junior-2.0-Windows-x86_64-Setup.exe"
    if not installer.is_file():
        raise FileNotFoundError(f"Inno Setup did not create {installer}")
    print(f"Built {installer}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
