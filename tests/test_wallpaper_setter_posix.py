from types import SimpleNamespace

import wallpaper_setter as ws
import wallpaper_setter_posix as wsp


def _ok_call(calls):
    """Fake subprocess.run that records the command and always succeeds."""
    def run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout="", stderr="")
    return run


# ---------------------------------------------------------------------------
# POSIX backend — validation, dispatch routing, desktop integration
# ---------------------------------------------------------------------------

def test_posix_missing_file_returns_false(tmp_path):
    ok, msg = wsp.set_wallpaper(str(tmp_path / "does_not_exist.png"))
    assert ok is False
    assert "not found" in msg.lower()


def test_set_wallpaper_routes_to_posix_backend(monkeypatch):
    monkeypatch.setattr(ws, "IS_WINDOWS", False)
    monkeypatch.setattr(wsp, "set_wallpaper", lambda p: (True, "posix backend"))
    ok, msg = ws.set_wallpaper("whatever.png")
    assert ok is True
    assert msg == "posix backend"


def test_set_wallpaper_routes_to_windows_backend(monkeypatch):
    monkeypatch.setattr(ws, "IS_WINDOWS", True)
    monkeypatch.setattr(ws, "_set_wallpaper_windows", lambda p: (True, "windows backend"))
    ok, msg = ws.set_wallpaper("whatever.png")
    assert ok is True
    assert msg == "windows backend"


def test_gnome_session_uses_gsettings(monkeypatch, tmp_path):
    img = tmp_path / "wall.png"
    img.write_bytes(b"png")
    calls = []
    monkeypatch.setattr(wsp, "_is_macos", lambda: False)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "GNOME")
    monkeypatch.setattr(wsp.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(wsp.subprocess, "run", _ok_call(calls))

    ok, msg = wsp.set_wallpaper(str(img))
    assert ok is True
    sets = [c for c in calls if c[:2] == ["gsettings", "set"]]
    assert any(c[3] == "picture-uri" for c in sets)
    assert any("wall.png" in c[4] for c in sets)


def test_kde_session_prefers_plasma_apply_wallpaperimage(monkeypatch, tmp_path):
    img = tmp_path / "wall.png"
    img.write_bytes(b"png")
    calls = []

    def which(name):
        return f"/usr/bin/{name}" if name == "plasma-apply-wallpaperimage" else None

    monkeypatch.setattr(wsp, "_is_macos", lambda: False)
    monkeypatch.setenv("XDG_CURRENT_DESKTOP", "KDE")
    monkeypatch.setattr(wsp.shutil, "which", which)
    monkeypatch.setattr(wsp.subprocess, "run", _ok_call(calls))

    ok, msg = wsp.set_wallpaper(str(img))
    assert ok is True
    assert calls[0][0] == "plasma-apply-wallpaperimage"
    assert str(img) in calls[0][1]


def test_macos_falls_back_to_osascript(monkeypatch, tmp_path):
    img = tmp_path / "wall.png"
    img.write_bytes(b"png")
    calls = []
    monkeypatch.setattr(wsp, "_is_macos", lambda: True)
    monkeypatch.setattr(wsp, "_set_macos_appkit", lambda p: (False, "pyobjc unavailable"))
    monkeypatch.setattr(wsp.subprocess, "run", _ok_call(calls))

    ok, msg = wsp.set_wallpaper(str(img))
    assert ok is True
    assert calls and calls[0][0] == "osascript"
    assert "System Events" in " ".join(calls[0])


def test_linux_failure_lists_attempted_tools(monkeypatch, tmp_path):
    img = tmp_path / "wall.png"
    img.write_bytes(b"png")
    monkeypatch.setattr(wsp, "_is_macos", lambda: False)
    monkeypatch.delenv("XDG_CURRENT_DESKTOP", raising=False)
    monkeypatch.delenv("DESKTOP_SESSION", raising=False)
    monkeypatch.delenv("XDG_SESSION_DESKTOP", raising=False)
    monkeypatch.delenv("SWAYSOCK", raising=False)
    monkeypatch.setattr(wsp.shutil, "which", lambda name: None)

    ok, msg = wsp.set_wallpaper(str(img))
    assert ok is False
    assert "Could not set wallpaper" in msg


# ---------------------------------------------------------------------------
# Lock screen stays Windows-exclusive on every entry point
# ---------------------------------------------------------------------------

def test_lockscreen_is_windows_only(monkeypatch):
    monkeypatch.setattr(ws, "IS_WINDOWS", False)
    for call in (
        lambda: ws.apply_lockscreen("x.png"),
        lambda: ws.restore_lockscreen(),
        lambda: ws.set_lockscreen_elevated("x.png"),
        lambda: ws.clear_lockscreen_elevated(),
    ):
        ok, msg = call()
        assert ok is False
        assert "windows" in msg.lower()
