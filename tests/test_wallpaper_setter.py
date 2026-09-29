import ctypes
import json
import os
from types import SimpleNamespace

import wallpaper_setter as ws

# ---------------------------------------------------------------------------
# set_wallpaper — validation and mocked registry/API paths
# ---------------------------------------------------------------------------

def test_set_wallpaper_missing_file_returns_false(tmp_path):
    ok, msg = ws.set_wallpaper(str(tmp_path / "does_not_exist.png"))
    assert ok is False
    assert "not found" in msg.lower()


def _fake_registry(monkeypatch):
    key = object()
    monkeypatch.setattr(ws.winreg, "OpenKey", lambda *a, **k: key)
    monkeypatch.setattr(ws.winreg, "CreateKeyEx", lambda *a, **k: key)
    monkeypatch.setattr(ws.winreg, "SetValueEx", lambda *a: None)
    monkeypatch.setattr(ws.winreg, "CloseKey", lambda k: None)
    return key


def test_set_wallpaper_success_mocked(fake_env, monkeypatch, tmp_path):
    img = tmp_path / "wall.png"
    img.write_bytes(b"fake-png")

    _fake_registry(monkeypatch)
    monkeypatch.setattr(
        ws.ctypes,
        "windll",
        SimpleNamespace(
            user32=SimpleNamespace(SystemParametersInfoW=lambda *a: 1)
        ),
    )

    ok, msg = ws.set_wallpaper(str(img))
    assert ok is True
    assert "successfully" in msg.lower()


def test_set_wallpaper_spi_failure_returns_false(fake_env, monkeypatch, tmp_path):
    img = tmp_path / "wall.png"
    img.write_bytes(b"fake-png")

    _fake_registry(monkeypatch)
    monkeypatch.setattr(
        ws.ctypes,
        "windll",
        SimpleNamespace(
            user32=SimpleNamespace(SystemParametersInfoW=lambda *a: 0)
        ),
    )
    monkeypatch.setattr(ws.ctypes, "GetLastError", lambda: 5)

    ok, msg = ws.set_wallpaper(str(img))
    assert ok is False
    assert "SystemParametersInfoW" in msg


def test_set_wallpaper_registry_exception_returns_false(fake_env, monkeypatch, tmp_path):
    img = tmp_path / "wall.png"
    img.write_bytes(b"fake-png")

    def _boom(*a, **k):
        raise OSError("access denied")
    monkeypatch.setattr(ws.winreg, "OpenKey", _boom)

    ok, msg = ws.set_wallpaper(str(img))
    assert ok is False
    assert "exception" in msg.lower() or "access denied" in msg.lower()


def test_set_wallpaper_uses_absolute_path(fake_env, monkeypatch, tmp_path):
    img = tmp_path / "wall.png"
    img.write_bytes(b"fake-png")

    captured = {}
    key = object()
    monkeypatch.setattr(ws.winreg, "OpenKey", lambda *a, **k: key)
    monkeypatch.setattr(ws.winreg, "CreateKeyEx", lambda *a, **k: key)

    def _capture(k, name, res, typ, val):
        if name == "Wallpaper":
            captured["path"] = val
    monkeypatch.setattr(ws.winreg, "SetValueEx", _capture)
    monkeypatch.setattr(ws.winreg, "CloseKey", lambda k: None)
    monkeypatch.setattr(
        ws.ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(SystemParametersInfoW=lambda *a: 1)),
    )

    # Relative path via chdir would be flaky; pass absolute and verify abspath used
    ok, _ = ws.set_wallpaper(str(img))
    assert ok is True
    assert os.path.isabs(captured["path"])
    assert captured["path"].endswith("wall.png")


def test_set_wallpaper_forces_picture_background_mode(fake_env, monkeypatch, tmp_path):
    img = tmp_path / "wall.png"
    img.write_bytes(b"fake-png")

    key = object()
    writes = []
    monkeypatch.setattr(ws.winreg, "OpenKey", lambda *a, **k: key)
    monkeypatch.setattr(ws.winreg, "CreateKeyEx", lambda *a, **k: key)
    monkeypatch.setattr(
        ws.winreg,
        "SetValueEx",
        lambda k, name, res, typ, val: writes.append((name, typ, val)),
    )
    monkeypatch.setattr(ws.winreg, "CloseKey", lambda k: None)
    monkeypatch.setattr(
        ws.ctypes,
        "windll",
        SimpleNamespace(user32=SimpleNamespace(SystemParametersInfoW=lambda *a: 1)),
    )

    ok, _ = ws.set_wallpaper(str(img))
    assert ok is True
    # BackgroundType DWORD 0 = Picture
    assert ("BackgroundType", ws.winreg.REG_DWORD, 0) in writes
    # WallpaperStyle 10 = Fill
    assert ("WallpaperStyle", ws.winreg.REG_SZ, "10") in writes
    assert ("TileWallpaper", ws.winreg.REG_SZ, "0") in writes


# ---------------------------------------------------------------------------
# Lock screen result-file IPC
# ---------------------------------------------------------------------------

def test_write_lockscreen_result_ok(fake_env):
    ws.write_lockscreen_result(True, "all good")
    p = fake_env.data / "lockscreen_result.json"
    assert p.exists()
    data = json.loads(p.read_text(encoding="utf-8"))
    assert data == {"ok": True, "msg": "all good"}


def test_write_lockscreen_result_failure(fake_env):
    ws.write_lockscreen_result(False, "denied")
    data = json.loads(
        (fake_env.data / "lockscreen_result.json").read_text(encoding="utf-8")
    )
    assert data == {"ok": False, "msg": "denied"}


def test_write_lockscreen_result_coerces_types(fake_env):
    ws.write_lockscreen_result(1, 12345)
    data = json.loads(
        (fake_env.data / "lockscreen_result.json").read_text(encoding="utf-8")
    )
    assert data == {"ok": True, "msg": "12345"}


def test_write_lockscreen_result_swallows_io_error(monkeypatch, tmp_path):
    # Path in a non-existent directory -> open() raises, must not propagate
    bad = str(tmp_path / "no_such_dir" / "sub" / "result.json")
    monkeypatch.setattr(ws, "LOCK_RESULT_FILE", bad)
    ws.write_lockscreen_result(True, "msg")  # must not raise


# ---------------------------------------------------------------------------
# Elevated helpers — path safety without requiring admin
# ---------------------------------------------------------------------------

def test_set_lockscreen_elevated_missing_image(tmp_path):
    ok, msg = ws.set_lockscreen_elevated(str(tmp_path / "missing.jpg"))
    assert ok is False
    assert "not found" in msg.lower()


def test_run_admin_mode_builds_frozen_command(monkeypatch):
    monkeypatch.setattr(ws.paths, "is_frozen", lambda: True)
    monkeypatch.setattr("sys.executable", "C:\\App\\YearProgress.exe")

    launched = {}

    def _fake_shell(info, op, file, params, dir_, show):
        launched["file"] = file
        launched["params"] = params
        return 42  # > 32 means success

    monkeypatch.setattr(
        ws.ctypes, "windll", SimpleNamespace(shell32=SimpleNamespace(ShellExecuteW=_fake_shell))
    )

    ok, err = ws._run_admin_mode("--lockscreen", "C:\\img\\a.png")
    assert ok is True
    assert err is None
    assert launched["file"] == "C:\\App\\YearProgress.exe"
    assert "--lockscreen" in launched["params"]
    assert "C:\\img\\a.png" in launched["params"]


def test_run_admin_mode_failure_when_shell_returns_low(monkeypatch):
    monkeypatch.setattr(ws.paths, "is_frozen", lambda: True)
    monkeypatch.setattr("sys.executable", "C:\\App\\YearProgress.exe")
    monkeypatch.setattr(
        ws.ctypes,
        "windll",
        SimpleNamespace(shell32=SimpleNamespace(ShellExecuteW=lambda *a: 5)),
    )

    ok, err = ws._run_admin_mode("--lockscreen")
    assert ok is False
    assert "cancelled" in err.lower() or "elevation" in err.lower()


def test_run_admin_and_wait_timeout(fake_env, monkeypatch):
    # Launch succeeds but no result file ever appears -> timeout
    monkeypatch.setattr(ws, "_run_admin_mode", lambda mode, arg=None: (True, None))
    monkeypatch.setattr(ws.time, "time", _fast_clock())

    ok, msg = ws._run_admin_and_wait("--lockscreen", "x.jpg", timeout=0.3)
    assert ok is False
    assert "timed out" in msg.lower()


def test_run_admin_and_wait_reads_result(fake_env, monkeypatch):
    result_path = str(fake_env.data / "lockscreen_result.json")

    def _fake_launch(mode, arg=None):
        with open(result_path, "w", encoding="utf-8") as f:
            json.dump({"ok": True, "msg": "lock set"}, f)
        return True, None

    monkeypatch.setattr(ws, "_run_admin_mode", _fake_launch)

    ok, msg = ws._run_admin_and_wait("--lockscreen", "x.jpg", timeout=2.0)
    assert ok is True
    assert msg == "lock set"


def test_run_admin_and_wait_propagates_launch_failure(monkeypatch):
    monkeypatch.setattr(ws, "_run_admin_mode", lambda mode, arg=None: (False, "user declined"))
    ok, msg = ws._run_admin_and_wait("--lockscreen")
    assert ok is False
    assert msg == "user declined"


def _fast_clock():
    """Return a callable that advances quickly so timeouts don't hang tests."""
    t = [0.0]

    def now():
        t[0] += 0.1
        return t[0]

    return now


def test_run_admin_and_wait_clears_stale_result_file(fake_env, monkeypatch):
    stale = fake_env.data / "lockscreen_result.json"
    stale.write_text('{"ok": true, "msg": "stale"}', encoding="utf-8")

    seen = {}

    def _fake_launch(mode, arg=None):
        seen["stale_gone"] = not stale.exists()
        with open(str(stale), "w", encoding="utf-8") as f:
            json.dump({"ok": False, "msg": "fresh"}, f)
        return True, None

    monkeypatch.setattr(ws, "_run_admin_mode", _fake_launch)
    ok, msg = ws._run_admin_and_wait("--lockscreen", "x.jpg", timeout=2.0)
    assert seen["stale_gone"] is True
    assert ok is False
    assert msg == "fresh"


# ---------------------------------------------------------------------------
# Regression: elevated relaunch command construction + registry key hygiene
# ---------------------------------------------------------------------------

def _capture_shell(monkeypatch):
    launched = {}

    def _fake_shell(info, op, file, params, dir_, show):
        launched["file"] = file
        launched["params"] = params
        return 42

    monkeypatch.setattr(
        ws.ctypes,
        "windll",
        SimpleNamespace(shell32=SimpleNamespace(ShellExecuteW=_fake_shell)),
    )
    return launched, _fake_shell


def test_run_admin_mode_frozen_params_do_not_repeat_executable(monkeypatch):
    monkeypatch.setattr(ws.paths, "is_frozen", lambda: True)
    monkeypatch.setattr("sys.executable", "C:\\App\\YearProgress.exe")
    launched, fake_shell = _capture_shell(monkeypatch)

    ok, err = ws._run_admin_mode("--lockscreen", "C:\\img\\a.png")

    assert ok is True and err is None
    # Windows builds the child command line as: "lpFile" lpParameters, and the
    # child argv then starts with argv[0] = lpFile. Repeating the exe inside
    # lpParameters makes the elevated child open its own executable as a script
    # and die before doing any work.
    assert launched["params"] == '--lockscreen "C:\\img\\a.png"'
    assert "YearProgress.exe" not in launched["params"]
    # HINSTANCE is a pointer: the return type must be widened or a truncated
    # value can look like a failure (<= 32).
    assert fake_shell.restype is ctypes.c_void_p


def test_run_admin_mode_dev_params_start_with_script(monkeypatch, tmp_path):
    monkeypatch.setattr(ws.paths, "is_frozen", lambda: False)
    monkeypatch.setattr(ws.paths, "app_dir", lambda: str(tmp_path))
    (tmp_path / "main.py").write_text("# entry", encoding="utf-8")
    monkeypatch.setattr("sys.executable", "C:\\Py\\python.exe")
    launched, _ = _capture_shell(monkeypatch)

    ok, err = ws._run_admin_mode("--lockscreen-clear")

    assert ok is True and err is None
    assert launched["file"] == "C:\\Py\\python.exe"
    assert launched["params"] == f'"{tmp_path / "main.py"}" --lockscreen-clear'


def test_set_wallpaper_closes_registry_key_when_write_fails(fake_env, monkeypatch, tmp_path):
    img = tmp_path / "wall.png"
    img.write_bytes(b"fake-png")
    closed = []
    monkeypatch.setattr(ws.winreg, "OpenKey", lambda *a, **k: object())
    monkeypatch.setattr(ws.winreg, "CloseKey", lambda k: closed.append(k))

    def _boom(*a, **k):
        raise OSError("access denied")

    monkeypatch.setattr(ws.winreg, "SetValueEx", _boom)

    ok, msg = ws.set_wallpaper(str(img))
    assert ok is False
    assert "access denied" in msg
    assert len(closed) == 1

