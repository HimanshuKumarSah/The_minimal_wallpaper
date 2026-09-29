import os
import sys


def is_frozen():
    """True when running from a PyInstaller-bundled executable."""
    return bool(getattr(sys, "frozen", False))


def resource_dir():
    """
    Directory of bundled, read-only resources (web/, assets/fonts, app_icon.png).
    When frozen this is the PyInstaller _MEI extraction folder; otherwise the
    source folder.
    """
    if is_frozen():
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def app_dir():
    """
    Stable directory containing the application / executable.
    When frozen this is the folder holding YearProgress.exe (never the temp
    _MEI extraction folder, which is deleted on exit).
    """
    if is_frozen():
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    """
    Writable, persistent per-user data directory for settings.json,
    quotes.json, and generated wallpaper files.

    Windows:   %LOCALAPPDATA%\\YearProgressWallpaper
    macOS:     ~/Library/Application Support/YearProgressWallpaper
    Linux:     $XDG_DATA_HOME/YearProgressWallpaper (default ~/.local/share/...)
    """
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or os.path.join(
            os.path.expanduser("~"), "AppData", "Local"
        )
    elif sys.platform == "darwin":
        base = os.path.join(os.path.expanduser("~"), "Library", "Application Support")
    else:
        base = os.environ.get("XDG_DATA_HOME") or os.path.join(
            os.path.expanduser("~"), ".local", "share"
        )
    d = os.path.join(base, "YearProgressWallpaper")
    try:
        os.makedirs(d, exist_ok=True)
    except OSError as e:
        print(f"Warning: could not create data dir {d}: {e}")
    return d