import sys

import paths
import startup_manager as sm


def test_app_name_and_run_key():
    assert sm.APP_NAME == "YearProgressWallpaper"
    assert "CurrentVersion\\Run" in sm.REG_RUN_KEY


def test_startup_command_prefers_exe(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "app_dir", lambda: str(tmp_path))
    (tmp_path / "YearProgress.exe").write_bytes(b"MZ")

    cmd = sm.get_startup_command()
    assert cmd == f'"{tmp_path / "YearProgress.exe"}" --minimized'
    # Exactly one quoted path (the exe), the flag is outside the quotes
    assert cmd.count('"') == 2
    assert cmd.endswith(" --minimized")
    assert "--minimized" in cmd


def test_startup_command_dev_mode_uses_python(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "app_dir", lambda: str(tmp_path))
    (tmp_path / "main.py").write_text("# entry", encoding="utf-8")
    # Mixed-case interpreter name: the python.exe detection must not lowercase
    # the whole path, and no sibling pythonw.exe exists here.
    fake_python = tmp_path / "Python.EXE"
    fake_python.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(fake_python))

    cmd = sm.get_startup_command()
    assert cmd == f'"{fake_python}" "{tmp_path / "main.py"}" --minimized'
    assert str(fake_python) in cmd
    assert "--minimized" in cmd


def test_startup_command_dev_mode_prefers_pythonw(monkeypatch, tmp_path):
    monkeypatch.setattr(paths, "app_dir", lambda: str(tmp_path))
    (tmp_path / "main.py").write_text("# entry", encoding="utf-8")

    # Simulate a python.exe interpreter with a sibling pythonw.exe
    fake_python = tmp_path / "python.exe"
    fake_pythonw = tmp_path / "pythonw.exe"
    fake_python.write_bytes(b"")
    fake_pythonw.write_bytes(b"")
    monkeypatch.setattr(sys, "executable", str(fake_python))

    cmd = sm.get_startup_command()
    assert "pythonw.exe" in cmd.lower()
    assert "main.py" in cmd


# ---------------------------------------------------------------------------
# Registry operations (mocked — never touch the real HKCU)
# ---------------------------------------------------------------------------

class FakeKey:
    def __init__(self):
        self.closed = False


def _patch_registry_ok(monkeypatch, *, value_exists=True):
    key = FakeKey()
    monkeypatch.setattr(sm.winreg, "OpenKey", lambda *a, **k: key)
    monkeypatch.setattr(sm.winreg, "CloseKey", lambda k: setattr(k, "closed", True))

    if value_exists:
        monkeypatch.setattr(
            sm.winreg, "QueryValueEx", lambda k, name: (f'"{sm.REG_RUN_KEY}"', 1)
        )
    else:
        def _missing(k, name):
            raise FileNotFoundError
        monkeypatch.setattr(sm.winreg, "QueryValueEx", _missing)

    return key


def test_is_startup_enabled_true(monkeypatch):
    _patch_registry_ok(monkeypatch, value_exists=True)
    assert sm.is_startup_enabled() is True


def test_is_startup_enabled_false_when_missing(monkeypatch):
    _patch_registry_ok(monkeypatch, value_exists=False)
    assert sm.is_startup_enabled() is False


def test_is_startup_enabled_false_on_error(monkeypatch):
    def _boom(*a, **k):
        raise OSError("registry unavailable")
    monkeypatch.setattr(sm.winreg, "OpenKey", _boom)
    assert sm.is_startup_enabled() is False


def test_set_startup_enable_writes_value(monkeypatch):
    key = FakeKey()
    written = {}

    monkeypatch.setattr(sm.winreg, "OpenKey", lambda *a, **k: key)
    monkeypatch.setattr(sm.winreg, "CloseKey", lambda k: setattr(k, "closed", True))
    monkeypatch.setattr(
        sm.winreg,
        "SetValueEx",
        lambda k, name, res, typ, val: written.update({"name": name, "val": val}),
    )
    monkeypatch.setattr(sm, "get_startup_command", lambda: '"C:\\app.exe" --minimized')

    ok, msg = sm.set_startup(True)
    assert ok is True
    assert written["name"] == sm.APP_NAME
    assert written["val"] == '"C:\\app.exe" --minimized'
    assert "Startup enabled" in msg
    assert key.closed is True


def test_set_startup_disable_deletes_value(monkeypatch):
    key = FakeKey()
    deleted = []

    monkeypatch.setattr(sm.winreg, "OpenKey", lambda *a, **k: key)
    monkeypatch.setattr(sm.winreg, "CloseKey", lambda k: setattr(k, "closed", True))
    monkeypatch.setattr(
        sm.winreg, "DeleteValue", lambda k, name: deleted.append(name)
    )

    ok, msg = sm.set_startup(False)
    assert ok is True
    assert deleted == [sm.APP_NAME]
    assert "Startup disabled" in msg
    assert key.closed is True


def test_set_startup_disable_missing_value_still_ok(monkeypatch):
    key = FakeKey()
    monkeypatch.setattr(sm.winreg, "OpenKey", lambda *a, **k: key)
    monkeypatch.setattr(sm.winreg, "CloseKey", lambda k: setattr(k, "closed", True))

    def _missing(k, name):
        raise FileNotFoundError
    monkeypatch.setattr(sm.winreg, "DeleteValue", _missing)

    ok, msg = sm.set_startup(False)
    assert ok is True
    assert "Startup disabled" in msg


def test_set_startup_error_returns_false(monkeypatch):
    def _boom(*a, **k):
        raise OSError("access denied")
    monkeypatch.setattr(sm.winreg, "OpenKey", _boom)

    ok, msg = sm.set_startup(True)
    assert ok is False
    assert "Failed" in msg


def test_is_startup_enabled_closes_key_on_success(monkeypatch):
    key = _patch_registry_ok(monkeypatch, value_exists=True)
    assert sm.is_startup_enabled() is True
    assert key.closed is True


def test_set_startup_closes_key_when_write_fails(monkeypatch):
    key = FakeKey()
    monkeypatch.setattr(sm.winreg, "OpenKey", lambda *a, **k: key)
    monkeypatch.setattr(sm.winreg, "CloseKey", lambda k: setattr(k, "closed", True))

    def _boom(*a, **k):
        raise OSError("access denied")

    monkeypatch.setattr(sm.winreg, "SetValueEx", _boom)

    ok, msg = sm.set_startup(True)
    assert ok is False
    assert "Failed" in msg
    assert key.closed is True
