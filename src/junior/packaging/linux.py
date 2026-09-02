"""Build Junior as an installable Debian package."""

import platform
import shutil
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
    application = repository / "dist" / "Junior 2.0"
    architecture = platform.machine().lower() or "unknown"
    deb_architecture = {"x86_64": "amd64", "aarch64": "arm64"}.get(
        architecture, architecture
    )
    package_root = repository / "build" / "junior2-deb"
    if package_root.exists():
        shutil.rmtree(package_root)
    install_root = package_root / "opt" / "junior2"
    shutil.copytree(application, install_root)
    binary = install_root / "Junior 2.0"
    binary.chmod(0o755)
    desktop = package_root / "usr" / "share" / "applications"
    desktop.mkdir(parents=True)
    (desktop / "junior2.desktop").write_text(
        "[Desktop Entry]\nName=Junior 2.0\nExec=/opt/junior2/Junior 2.0\n"
        "Icon=junior2\nType=Application\nCategories=Utility;\n",
        encoding="utf-8",
    )
    icons = package_root / "usr" / "share" / "icons" / "hicolor" / "512x512" / "apps"
    icons.mkdir(parents=True)
    shutil.copy2(repository / "assets" / "Junior.png", icons / "junior2.png")
    control = package_root / "DEBIAN"
    control.mkdir()
    (control / "control").write_text(
        "Package: junior2\nVersion: 2.0.0\nSection: utils\nPriority: optional\n"
        f"Architecture: {deb_architecture}\nMaintainer: Junior\n"
        "Description: Junior 2.0 local-first job discovery application\n",
        encoding="utf-8",
    )
    package = repository / "dist" / f"Junior-2.0-Linux-{architecture}.deb"
    subprocess.run(["dpkg-deb", "--build", str(package_root), str(package)], check=True)
    print(f"Built {package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
