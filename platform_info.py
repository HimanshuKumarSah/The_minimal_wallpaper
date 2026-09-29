"""Operating-system detection with user-facing labels for each platform.

Single source of truth for "which OS are we on" and the wording the UIs use
(tray menu, Tk control panel, web control panel). Feature flags live here so
both front ends can hide Windows-only capabilities on other platforms.
"""

import sys

IS_WINDOWS = sys.platform == "win32"
IS_MACOS = sys.platform == "darwin"

OS_NAME = "windows" if IS_WINDOWS else ("macos" if IS_MACOS else "linux")

# The lock screen image can only be forced through the Windows registry
# (HKLM PersonalizationCSP), so the feature is Windows-exclusive.
SUPPORTS_LOCKSCREEN = IS_WINDOWS

if IS_WINDOWS:
    STARTUP_LABEL = "Run at Windows Startup"
    STARTUP_TITLE = "Launch with Windows"
    STARTUP_NOTE = "Registered in Windows Registry — HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run"
    STARTUP_CARD_HEADER = "WINDOWS STARTUP INTEGRATION"
    STARTUP_SWITCH_TEXT = "Start automatically on Windows boot (runs in tray)"
elif IS_MACOS:
    STARTUP_LABEL = "Run at Startup"
    STARTUP_TITLE = "Launch at startup"
    STARTUP_NOTE = "Installed as a Launch Agent — ~/Library/LaunchAgents"
    STARTUP_CARD_HEADER = "LOGIN STARTUP"
    STARTUP_SWITCH_TEXT = "Start automatically at login (runs in tray)"
else:
    STARTUP_LABEL = "Run at Startup"
    STARTUP_TITLE = "Launch at startup"
    STARTUP_NOTE = "Installed as an XDG autostart entry — ~/.config/autostart"
    STARTUP_CARD_HEADER = "LOGIN STARTUP"
    STARTUP_SWITCH_TEXT = "Start automatically at login (runs in tray)"


def as_dict():
    """Serializable platform payload for the web control panel."""
    return {
        "os": OS_NAME,
        "lockscreen": SUPPORTS_LOCKSCREEN,
        "startup_title": STARTUP_TITLE,
        "startup_note": STARTUP_NOTE,
    }
