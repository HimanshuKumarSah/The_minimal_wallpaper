import sys
from types import SimpleNamespace

import pytest

# `pythonpath = .` in pytest.ini puts the project root on sys.path before this
# file is imported, so the app modules below resolve without a manual bootstrap.
import config
import paths
import wallpaper_setter

# Suites that drive the Windows registry / SystemParametersInfo / UAC elevation
# internals. They are collected everywhere but only executed on Windows; the
# cross-platform behaviour is covered by the *_posix test modules instead.
WINDOWS_ONLY_MODULES = {"test_wallpaper_setter", "test_startup_manager"}


def pytest_collection_modifyitems(config, items):
    if sys.platform == "win32":
        return
    skip_windows = pytest.mark.skip(
        reason="Windows-only internals (registry / SPI / UAC elevation)"
    )
    for item in items:
        if item.path.stem in WINDOWS_ONLY_MODULES:
            item.add_marker(skip_windows)


@pytest.fixture
def fake_env(tmp_path, monkeypatch):
    """Isolate all file I/O (settings, quotes, wallpapers) to a temp directory."""
    data = tmp_path / "data"
    resources = tmp_path / "resources"
    app = tmp_path / "app"
    for d in (data, resources, app):
        d.mkdir()

    monkeypatch.setattr(paths, "data_dir", lambda: str(data))
    monkeypatch.setattr(paths, "resource_dir", lambda: str(resources))
    monkeypatch.setattr(paths, "app_dir", lambda: str(app))
    monkeypatch.setattr(config, "SETTINGS_FILE", str(data / "settings.json"))
    monkeypatch.setattr(config, "QUOTES_FILE", str(data / "quotes.json"))
    monkeypatch.setattr(
        wallpaper_setter, "LOCK_RESULT_FILE", str(data / "lockscreen_result.json")
    )

    return SimpleNamespace(data=data, resources=resources, app=app, tmp_path=tmp_path)
