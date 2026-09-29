"""Desktop wallpaper control for macOS and Linux.

Windows keeps its registry + SystemParametersInfo implementation inside
wallpaper_setter.py. This module provides the same ``set_wallpaper(image_path)
-> (ok, message)`` contract for the POSIX platforms:

* macOS — NSWorkspace through pyobjc (pulled in by pywebview), with an
          osascript System Events fallback when pyobjc is unavailable.
* Linux — the running desktop's native wallpaper mechanism: gsettings for
          GNOME/Cinnamon/MATE, plasma-apply-wallpaperimage or the plasmashell
          scripting API for KDE, xfconf-query for Xfce; feh/swaymsg as
          fallbacks for bare window managers.
"""

import json
import os
import shutil
import subprocess
import sys


def set_wallpaper(image_path):
    """Sets the desktop wallpaper to ``image_path`` on macOS or Linux."""
    abs_path = os.path.abspath(image_path)
    if not os.path.exists(abs_path):
        return False, f"Wallpaper file not found: {abs_path}"
    if _is_macos():
        return _set_macos_wallpaper(abs_path)
    return _set_linux_wallpaper(abs_path)


def _is_macos():
    return sys.platform == "darwin"


def _run(cmd, timeout=15):
    """Runs a helper command and captures its output (never raises)."""
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout
        )
    except Exception as e:
        return SimpleRunResult(127, "", str(e))


class SimpleRunResult:
    """Stand-in for a CompletedProcess when a helper can't even start."""

    def __init__(self, returncode, stdout, stderr):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


# ==============================================================================
# macOS
# ==============================================================================

def _set_macos_wallpaper(abs_path):
    ok, msg = _set_macos_appkit(abs_path)
    if ok:
        return True, "Wallpaper updated successfully."
    return _set_macos_osascript(abs_path, msg)


def _set_macos_appkit(abs_path):
    """Preferred path: NSWorkspace needs no automation permission."""
    try:
        import AppKit
        from Foundation import NSURL
    except Exception as e:
        return False, f"pyobjc unavailable ({e})"
    try:
        workspace = AppKit.NSWorkspace.sharedWorkspace()
        url = NSURL.fileURLWithPath_(abs_path)
        screens = AppKit.NSScreen.screens()
        if not screens:
            return False, "no displays found"
        for screen in screens:
            result = workspace.setDesktopImageURL_forScreen_options_error_(
                url, screen, {}, None
            )
            # pyobjc may return the raw BOOL or a (result, error) tuple
            # depending on how the NSError** out-parameter is bridged.
            if isinstance(result, tuple):
                success, error = bool(result[0]), result[1]
                if not success:
                    return False, str(error or "rejected by NSWorkspace")
            elif not result:
                return False, "rejected by NSWorkspace"
        return True, ""
    except Exception as e:
        return False, f"NSWorkspace failed ({e})"


def _set_macos_osascript(abs_path, prior_error):
    """Fallback: System Events (may prompt for automation permission once)."""
    escaped = abs_path.replace("\\", "\\\\").replace('"', '\\"')
    script = (
        'tell application "System Events" to set picture of every desktop '
        f'to POSIX file "{escaped}"'
    )
    proc = _run(["osascript", "-e", script])
    if proc.returncode == 0:
        return True, "Wallpaper updated successfully."
    detail = (proc.stderr or proc.stdout or "").strip()
    return False, f"osascript failed ({detail or prior_error})"


# ==============================================================================
# Linux
# ==============================================================================

def _set_linux_wallpaper(abs_path):
    uri = "file://" + abs_path
    desktop = " ".join(
        filter(
            None,
            (
                os.environ.get("XDG_CURRENT_DESKTOP", ""),
                os.environ.get("DESKTOP_SESSION", ""),
                os.environ.get("XDG_SESSION_DESKTOP", ""),
            ),
        )
    ).lower()

    handlers = []
    if any(k in desktop for k in ("kde", "plasma")):
        handlers.append(("KDE Plasma", _set_kde))
    if any(k in desktop for k in ("gnome", "unity", "budgie", "pantheon")):
        handlers.append(("GNOME", _set_gnome))
    if "cinnamon" in desktop:
        handlers.append(("Cinnamon", _set_cinnamon))
    if "mate" in desktop:
        handlers.append(("MATE", _set_mate))
    if "xfce" in desktop:
        handlers.append(("Xfce", _set_xfce))
    # Generic probes: honour whatever tools actually exist on this system,
    # regardless of what the session claims to be.
    handlers += [
        ("GNOME", _set_gnome),
        ("KDE Plasma", _set_kde),
        ("Xfce", _set_xfce),
        ("sway", _set_sway),
        ("feh", _set_feh),
    ]

    attempts = []
    seen = set()
    for name, handler in handlers:
        if handler in seen:
            continue
        seen.add(handler)
        ok, err = handler(uri, abs_path)
        if ok:
            return True, f"Wallpaper updated successfully ({name})."
        attempts.append(f"{name}: {err}")
    return False, "Could not set wallpaper on this desktop — " + "; ".join(attempts)


def _gvariant_str(value):
    """Quotes a Python string as a GVariant text string for gsettings."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _gsettings_set(schema, key, value):
    proc = _run(["gsettings", "set", schema, key, value])
    return proc.returncode == 0, (proc.stderr or proc.stdout or "").strip()


def _set_gnome(uri, path):
    if not shutil.which("gsettings"):
        return False, "gsettings not found"
    ok, err = _gsettings_set("org.gnome.desktop.background", "picture-uri", _gvariant_str(uri))
    if not ok:
        return False, err or "gsettings set picture-uri failed"
    # GNOME 42+ dark-mode key and the scaling hint are best effort: older
    # releases simply don't know them and reply with an error we can ignore.
    _gsettings_set("org.gnome.desktop.background", "picture-uri-dark", _gvariant_str(uri))
    _gsettings_set("org.gnome.desktop.background", "picture-options", _gvariant_str("zoom"))
    return True, ""


def _set_cinnamon(uri, path):
    if not shutil.which("gsettings"):
        return False, "gsettings not found"
    ok, err = _gsettings_set("org.cinnamon.desktop.background", "picture-uri", _gvariant_str(uri))
    if not ok:
        return False, err or "gsettings set picture-uri failed"
    _gsettings_set("org.cinnamon.desktop.background", "picture-options", _gvariant_str("zoom"))
    return True, ""


def _set_mate(uri, path):
    if not shutil.which("gsettings"):
        return False, "gsettings not found"
    ok, err = _gsettings_set("org.mate.background", "picture-filename", _gvariant_str(path))
    if not ok:
        return False, err or "gsettings set picture-filename failed"
    return True, ""


def _set_kde(uri, path):
    if shutil.which("plasma-apply-wallpaperimage"):
        proc = _run(["plasma-apply-wallpaperimage", path])
        if proc.returncode == 0:
            return True, ""
        last_err = (proc.stderr or proc.stdout or "").strip()
    else:
        last_err = "plasma-apply-wallpaperimage not found"
    # Classic plasmashell scripting API, reachable through any qdbus variant.
    script = (
        "var ds = desktops();"
        "for (var i = 0; i < ds.length; i++) {"
        "  var d = ds[i];"
        "  d.wallpaperPlugin = 'org.kde.image';"
        "  d.currentConfigGroup = ['Wallpaper', 'org.kde.image', 'General'];"
        f"  d.writeConfig('Image', {json.dumps(uri)});"
        "}"
    )
    for qdbus in ("qdbus6", "qdbus", "qdbus-qt5"):
        if not shutil.which(qdbus):
            continue
        proc = _run(
            [
                qdbus,
                "org.kde.plasmashell",
                "/PlasmaShell",
                "org.kde.PlasmaShell.evaluateScript",
                script,
            ]
        )
        if proc.returncode == 0:
            return True, ""
        last_err = (proc.stderr or proc.stdout or "").strip() or last_err
    return False, last_err or "no KDE wallpaper tool available"


def _set_xfce(uri, path):
    if not shutil.which("xfconf-query"):
        return False, "xfconf-query not found"
    proc = _run(["xfconf-query", "-c", "xfce4-desktop", "-l"])
    if proc.returncode != 0:
        return False, (proc.stderr or proc.stdout or "").strip() or "xfconf-query failed"
    props = [
        line.strip()
        for line in proc.stdout.splitlines()
        if line.strip().rsplit("/", 1)[-1] in ("last-image", "image-path")
    ]
    if not props:
        return False, "no xfce4-desktop backdrop image property found"
    for prop in props:
        result = _run(["xfconf-query", "-c", "xfce4-desktop", "-p", prop, "-s", path])
        if result.returncode != 0:
            return False, (result.stderr or "").strip() or f"failed writing {prop}"
    return True, ""


def _set_sway(uri, path):
    if not os.environ.get("SWAYSOCK") or not shutil.which("swaymsg"):
        return False, "sway session not detected"
    proc = _run(["swaymsg", "output", "*", "bg", path, "fill"])
    return proc.returncode == 0, (proc.stderr or proc.stdout or "").strip()


def _set_feh(uri, path):
    if not shutil.which("feh"):
        return False, "feh not found"
    proc = _run(["feh", "--bg-fill", path])
    return proc.returncode == 0, (proc.stderr or proc.stdout or "").strip()
