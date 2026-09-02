from pathlib import Path
from unittest.mock import Mock, patch

from junior.packaging import linux, macos, windows
from junior.packaging.common import pyinstaller_arguments


def test_shared_package_includes_native_app_and_catalog() -> None:
    arguments = pyinstaller_arguments()

    assert "--windowed" in arguments
    assert arguments[arguments.index("--icon") + 1].endswith("assets/Junior.png")
    assert arguments[arguments.index("--collect-data") + 1] == "junior.catalog"
    assert arguments[-1].endswith("src/junior/__main__.py")


def test_windows_builder_creates_named_installer(tmp_path: Path) -> None:
    pyinstaller = Mock()
    installer = tmp_path / "dist/Junior-2.0-Windows-x86_64-Setup.exe"
    installer.parent.mkdir()
    installer.touch()
    with (
        patch.object(windows, "load_pyinstaller", return_value=pyinstaller),
        patch.object(windows, "repository_root", return_value=tmp_path),
        patch.object(windows.subprocess, "run") as run,
    ):
        assert windows.main() == 0

    pyinstaller.run.assert_called_once()
    assert run.call_args.kwargs["check"] is True
    assert "ISCC.exe" in run.call_args.args[0]


def test_linux_builder_creates_debian_installer(tmp_path: Path) -> None:
    pyinstaller = Mock()
    application = tmp_path / "dist/Junior 2.0"
    application.mkdir(parents=True)
    executable = application / "Junior 2.0"
    executable.touch()
    assets = tmp_path / "assets"
    assets.mkdir()
    (assets / "Junior.png").write_bytes(b"png")
    with (
        patch.object(linux, "load_pyinstaller", return_value=pyinstaller),
        patch.object(linux, "repository_root", return_value=tmp_path),
        patch.object(linux.platform, "machine", return_value="x86_64"),
        patch.object(linux.subprocess, "run") as run,
    ):
        assert linux.main() == 0

    pyinstaller.run.assert_called_once()
    assert run.call_args.args[0][-1] == str(
        tmp_path / "dist/Junior-2.0-Linux-x86_64.deb"
    )
    assert (tmp_path / "build/junior2-deb/DEBIAN/control").is_file()
    assert (
        tmp_path / "build/junior2-deb/usr/share/applications/junior2.desktop"
    ).is_file()


def test_macos_builder_supplies_bundle_identifier(tmp_path: Path) -> None:
    pyinstaller = Mock()
    (tmp_path / "build").mkdir()
    (tmp_path / "dist/Junior 2.0.app").mkdir(parents=True)
    with (
        patch.object(macos, "load_pyinstaller", return_value=pyinstaller),
        patch.object(macos, "repository_root", return_value=tmp_path),
        patch.object(macos.platform, "machine", return_value="arm64"),
        patch.object(macos.subprocess, "run"),
    ):
        assert macos.main() == 0

    arguments = pyinstaller.run.call_args.args[0]
    assert arguments[arguments.index("--osx-bundle-identifier") + 1] == (
        "com.juniorapp.junior2"
    )
    assert arguments[arguments.index("--icon") + 1] == str(
        tmp_path / "assets/Junior.icns"
    )


def test_macos_dmg_layout_has_applications_shortcut(tmp_path: Path) -> None:
    application = tmp_path / "Junior 2.0.app"
    application.mkdir()
    (application / "marker").write_text("native app")
    layout = tmp_path / "layout"
    layout.mkdir()

    macos._prepare_dmg_layout(layout, application)

    assert (layout / "Junior 2.0.app/marker").read_text() == "native app"
    assert (layout / "Applications").is_symlink()
    assert (layout / "Applications").readlink() == Path("/Applications")


def test_macos_bundle_is_versioned_and_resigned(tmp_path: Path) -> None:
    application = tmp_path / "Junior 2.0.app"
    (application / "Contents").mkdir(parents=True)
    (application / "Contents/Info.plist").touch()
    with patch.object(macos.subprocess, "run") as run:
        macos._stamp_and_sign_bundle(application)

    commands = [call.args[0] for call in run.call_args_list]
    assert any("CFBundleShortVersionString" in command for command in commands)
    assert any("CFBundleVersion" in command for command in commands)
    assert commands[-1][:4] == ["codesign", "--force", "--deep", "--sign"]
