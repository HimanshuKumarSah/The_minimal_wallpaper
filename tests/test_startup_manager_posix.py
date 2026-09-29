import startup_manager as sm
import startup_manager_posix as smp


def _isolate(monkeypatch, tmp_path, *, macos):
    monkeypatch.setattr(smp, "_is_macos", lambda: macos)
    # Set both: expanduser('~') consults HOME on POSIX and USERPROFILE on
    # Windows, and these tests must pass on either host.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    # Never let a test activate a real login item on the host machine.
    monkeypatch.setattr(smp.shutil, "which", lambda name: None)


# ---------------------------------------------------------------------------
# Linux — XDG autostart .desktop entry
# ---------------------------------------------------------------------------

def test_linux_autostart_enable_disable(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, macos=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))

    ok, msg = smp.set_startup(True)
    assert ok is True
    assert "Startup enabled" in msg

    entry = tmp_path / "cfg" / "autostart" / "YearProgressWallpaper.desktop"
    assert entry.exists()
    content = entry.read_text(encoding="utf-8")
    assert "[Desktop Entry]" in content
    assert "Type=Application" in content
    assert "Exec=" in content
    assert "--minimized" in content
    assert "Terminal=false" in content
    assert smp.is_startup_enabled() is True

    ok, msg = smp.set_startup(False)
    assert ok is True
    assert msg == "Startup disabled."
    assert not entry.exists()
    assert smp.is_startup_enabled() is False


def test_linux_autostart_default_location(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, macos=False)

    ok, _ = smp.set_startup(True)
    assert ok is True
    entry = tmp_path / ".config" / "autostart" / "YearProgressWallpaper.desktop"
    assert entry.exists()
    smp.set_startup(False)


def test_linux_disable_when_never_enabled_is_ok(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, macos=False)
    ok, msg = smp.set_startup(False)
    assert ok is True
    assert msg == "Startup disabled."


# ---------------------------------------------------------------------------
# macOS — LaunchAgent plist
# ---------------------------------------------------------------------------

def test_macos_launch_agent_enable_disable(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, macos=True)

    ok, msg = smp.set_startup(True)
    assert ok is True
    assert "Startup enabled" in msg

    plist = tmp_path / "Library" / "LaunchAgents" / "com.yearprogress.wallpaper.plist"
    assert plist.exists()
    content = plist.read_text(encoding="utf-8")
    assert "<key>Label</key>" in content
    assert "com.yearprogress.wallpaper" in content
    assert "ProgramArguments" in content
    assert "--minimized" in content
    assert "<key>RunAtLoad</key>" in content
    assert smp.is_startup_enabled() is True

    ok, msg = smp.set_startup(False)
    assert ok is True
    assert msg == "Startup disabled."
    assert not plist.exists()
    assert smp.is_startup_enabled() is False


def test_startup_command_and_arguments(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path, macos=False)
    monkeypatch.setattr(smp.paths, "app_dir", lambda: str(tmp_path))
    (tmp_path / "main.py").write_text("# entry", encoding="utf-8")

    cmd = smp.get_startup_command()
    assert "main.py" in cmd
    assert "--minimized" in cmd
    assert cmd.startswith('"')

    args = smp._launch_arguments()
    assert args[0] == str(tmp_path / "main.py") or args[1] == str(tmp_path / "main.py")
    assert args[-1] == "--minimized"


def test_exec_field_quotes_spaces_and_escapes_percent(monkeypatch, tmp_path):
    line = smp._exec_field(["/opt/My App/bin", "100%done"])
    assert line == '"/opt/My App/bin" 100%%done'


# ---------------------------------------------------------------------------
# Dispatch from the public startup_manager module
# ---------------------------------------------------------------------------

def test_dispatcher_routes_to_posix_backend(monkeypatch):
    monkeypatch.setattr(sm, "IS_WINDOWS", False)
    monkeypatch.setattr(smp, "is_startup_enabled", lambda: True)
    assert sm.is_startup_enabled() is True

    monkeypatch.setattr(smp, "set_startup", lambda enable=True: (True, "posix says hi"))
    ok, msg = sm.set_startup(True)
    assert ok is True
    assert msg == "posix says hi"

    monkeypatch.setattr(smp, "get_startup_command", lambda: "posix command")
    assert sm.get_startup_command() == "posix command"
