"""Auto-start registration for macOS (LaunchAgent) and Linux (XDG autostart).

Windows keeps its HKCU Run-key implementation inside startup_manager.py; this
module provides the same ``get_startup_command`` / ``is_startup_enabled`` /
``set_startup`` contract for the POSIX platforms:

* macOS — a LaunchAgent plist in ~/Library/LaunchAgents (loaded with
          launchctl when available, effective at the next login regardless).
* Linux — a .desktop entry in $XDG_CONFIG_HOME/autostart (or ~/.config/autostart),
          honoured by every XDG-compliant session manager.
"""

import os
import shutil
import subprocess
import sys
from xml.sax.saxutils import escape

import paths

APP_NAME = "YearProgressWallpaper"
LAUNCH_AGENT_LABEL = "com.yearprogress.wallpaper"


def get_startup_command():
    """Human-readable login command line (parity with the Windows helper)."""
    args = _launch_arguments()
    return '"{}" {}'.format(args[0], " ".join(args[1:]))


def is_startup_enabled():
    """True when the login entry (LaunchAgent / autostart file) exists."""
    path = _entry_path()
    if path is None:
        return False
    try:
        return os.path.getsize(path) > 0
    except OSError:
        return False


def set_startup(enable=True):
    """Creates or removes the login entry for the current user."""
    try:
        if enable:
            path = _write_entry()
            _register_now(path)
            return True, f"Startup enabled: {path}"
        path = _remove_entry()
        _unregister_now()
        return True, "Startup disabled."
    except OSError as e:
        return False, f"Failed to update startup entry: {e}"


# ==============================================================================
# Internals
# ==============================================================================

def _is_macos():
    return sys.platform == "darwin"


def _home():
    return os.path.expanduser("~")


def _launch_agent_path():
    return os.path.join(_home(), "Library", "LaunchAgents", f"{LAUNCH_AGENT_LABEL}.plist")


def _autostart_path():
    base = os.environ.get("XDG_CONFIG_HOME") or os.path.join(_home(), ".config")
    return os.path.join(base, "autostart", f"{APP_NAME}.desktop")


def _entry_path():
    """Path of the login entry for the current platform (None if N/A)."""
    if _is_macos():
        return _launch_agent_path()
    return _autostart_path()


def _launch_arguments():
    """argv the login entry should execute (frozen binary or source tree)."""
    if paths.is_frozen():
        name = "YearProgress.exe" if sys.platform == "win32" else "YearProgress"
        return [os.path.join(paths.app_dir(), name), "--minimized"]
    return [sys.executable, os.path.join(paths.app_dir(), "main.py"), "--minimized"]


def _write_entry():
    if _is_macos():
        path = _launch_agent_path()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(_launch_agent_plist())
        return path
    path = _autostart_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(_autostart_desktop_entry())
    return path


def _remove_entry():
    path = _entry_path()
    try:
        os.remove(path)
    except FileNotFoundError:
        pass
    return path


def _launch_agent_plist():
    arg_lines = "".join(
        f"        <string>{escape(a)}</string>\n" for a in _launch_arguments()
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        "<dict>\n"
        "    <key>Label</key>\n"
        f"    <string>{LAUNCH_AGENT_LABEL}</string>\n"
        "    <key>ProgramArguments</key>\n"
        "    <array>\n"
        f"{arg_lines}"
        "    </array>\n"
        "    <key>RunAtLoad</key>\n"
        "    <true/>\n"
        "</dict>\n"
        "</plist>\n"
    )


def _autostart_desktop_entry():
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Year Progress Wallpaper\n"
        "Comment=Generate and apply the year progress wallpaper at login\n"
        f"Exec={_exec_field(_launch_arguments())}\n"
        "Terminal=false\n"
        "X-GNOME-Autostart-enabled=true\n"
    )


def _exec_field(args):
    """Formats argv for a desktop-entry Exec= line (spaces quoted, % escaped)."""
    parts = []
    for arg in args:
        if any(ch in arg for ch in ' \t"'):
            parts.append('"' + arg.replace("\\", "\\\\").replace('"', '\\"') + '"')
        else:
            parts.append(arg)
    return " ".join(parts).replace("%", "%%")


def _register_now(path):
    """Best effort: activate the entry without waiting for the next login."""
    if _is_macos() and shutil.which("launchctl"):
        subprocess.run(
            ["launchctl", "bootstrap", f"gui/{os.getuid()}", path],
            capture_output=True,
            timeout=10,
        )


def _unregister_now():
    if _is_macos() and shutil.which("launchctl"):
        subprocess.run(
            ["launchctl", "bootout", f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"],
            capture_output=True,
            timeout=10,
        )
