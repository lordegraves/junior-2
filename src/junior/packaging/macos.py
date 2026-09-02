"""Build Junior as a self-contained macOS application bundle."""

import platform
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from junior.packaging.common import (
    load_pyinstaller,
    pyinstaller_arguments,
    repository_root,
)


def main() -> int:
    pyinstaller = load_pyinstaller()
    repository = repository_root()
    arguments = pyinstaller_arguments()
    icon_index = arguments.index("--icon")
    del arguments[icon_index : icon_index + 2]
    arguments[4:4] = [
        "--osx-bundle-identifier",
        "com.juniorapp.junior2",
        "--icon",
        str(repository / "assets" / "Junior.icns"),
    ]
    pyinstaller.run(arguments)
    app = repository / "dist" / "Junior 2.0.app"
    _stamp_and_sign_bundle(app)
    print(f"Built {app}")
    architecture = platform.machine().lower() or "unknown"
    dmg = repository / "dist" / f"Junior-2.0-macOS-{architecture}.dmg"
    with TemporaryDirectory(prefix="junior-dmg-", dir=repository / "build") as temp:
        layout = Path(temp)
        _prepare_dmg_layout(layout, app)
        subprocess.run(
            [
                "hdiutil",
                "create",
                "-volname",
                "Junior 2.0",
                "-srcfolder",
                str(layout),
                "-ov",
                "-format",
                "UDZO",
                str(dmg),
            ],
            check=True,
        )
    print(f"Built {dmg}")
    return 0


def _prepare_dmg_layout(layout: Path, application: Path) -> None:
    shutil.copytree(application, layout / application.name)
    (layout / "Applications").symlink_to("/Applications", target_is_directory=True)


def _stamp_and_sign_bundle(application: Path) -> None:
    plist = application / "Contents" / "Info.plist"
    subprocess.run(
        [
            "plutil",
            "-replace",
            "CFBundleShortVersionString",
            "-string",
            "2.0.0",
            str(plist),
        ],
        check=True,
    )
    subprocess.run(
        [
            "plutil",
            "-replace",
            "CFBundleVersion",
            "-string",
            "2.0.0.1",
            str(plist),
        ],
        check=True,
    )
    subprocess.run(
        ["codesign", "--force", "--deep", "--sign", "-", str(application)],
        check=True,
    )


if __name__ == "__main__":
    raise SystemExit(main())
