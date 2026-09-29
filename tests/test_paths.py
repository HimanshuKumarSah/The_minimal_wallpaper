import os
import sys

import paths


def test_is_frozen_default_false():
    assert paths.is_frozen() is False


def test_is_frozen_when_sys_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    assert paths.is_frozen() is True


def test_resource_dir_source_is_module_dir():
    d = paths.resource_dir()
    assert os.path.isdir(d)
    assert os.path.exists(os.path.join(d, "paths.py"))


def test_app_dir_source_is_module_dir():
    d = paths.app_dir()
    assert os.path.isdir(d)
    assert os.path.exists(os.path.join(d, "main.py"))


def test_resource_dir_frozen_uses_meipass(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", "C:/fake/mei", raising=False)
    assert paths.resource_dir() == "C:/fake/mei"


def test_app_dir_frozen_uses_executable_dir(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    expected = os.path.dirname(sys.executable)
    assert paths.app_dir() == expected


def test_data_dir_uses_localappdata(monkeypatch, tmp_path):
    base = tmp_path / "LocalAppData"
    with monkeypatch.context() as m:
        m.setattr(sys, "platform", "win32")
        m.setenv("LOCALAPPDATA", str(base))
        d = paths.data_dir()
    assert d == os.path.join(str(base), "YearProgressWallpaper")
    assert os.path.isdir(d)


def test_data_dir_falls_back_to_home(monkeypatch):
    with monkeypatch.context() as m:
        m.setattr(sys, "platform", "win32")
        m.delenv("LOCALAPPDATA", raising=False)
        d = paths.data_dir()
    assert d.endswith(os.path.join("YearProgressWallpaper"))
    assert os.path.isdir(d)


def test_data_dir_idempotent(monkeypatch, tmp_path):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "lad"))
    d1 = paths.data_dir()
    d2 = paths.data_dir()
    assert d1 == d2
    assert os.path.isdir(d1)


# ---------------------------------------------------------------------------
# Non-Windows data directory locations
# ---------------------------------------------------------------------------

def test_data_dir_macos_uses_application_support(monkeypatch, tmp_path):
    with monkeypatch.context() as m:
        m.setattr(sys, "platform", "darwin")
        m.setenv("HOME", str(tmp_path))
        m.setenv("USERPROFILE", str(tmp_path))
        d = paths.data_dir()
    assert d == os.path.join(
        str(tmp_path), "Library", "Application Support", "YearProgressWallpaper"
    )
    assert os.path.isdir(d)


def test_data_dir_linux_uses_xdg_data_home(monkeypatch, tmp_path):
    with monkeypatch.context() as m:
        m.setattr(sys, "platform", "linux")
        m.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        d = paths.data_dir()
    assert d == os.path.join(str(tmp_path / "xdg"), "YearProgressWallpaper")
    assert os.path.isdir(d)


def test_data_dir_linux_defaults_to_local_share(monkeypatch, tmp_path):
    with monkeypatch.context() as m:
        m.setattr(sys, "platform", "linux")
        m.delenv("XDG_DATA_HOME", raising=False)
        m.setenv("HOME", str(tmp_path))
        m.setenv("USERPROFILE", str(tmp_path))
        d = paths.data_dir()
    assert d == os.path.join(str(tmp_path), ".local", "share", "YearProgressWallpaper")
    assert os.path.isdir(d)
