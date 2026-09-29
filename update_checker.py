"""Optional GitHub Releases update check (once a day, tray notification).

Pure stdlib — no third-party HTTP client — so it works identically in the
frozen exe and from source. All network failures are swallowed: an update check
must never be able to break wallpaper updates.
"""

import datetime
import json
import urllib.request

import config

RELEASES_URL = (
    "https://api.github.com/repos/HimanshuKumarSah/"
    "The_minimal_wallpaper/releases/latest"
)
_TIMEOUT = 6.0

# Newest release seen by the current process (None until a check runs).
_latest = {"info": None}


def _parse_version(tag):
    """'v1.2.3' / '1.2.3' -> (1, 2, 3); None when unparseable."""
    if not tag:
        return None
    text = str(tag).strip().lstrip("vV")
    parts = text.split(".")
    numbers = []
    for part in parts[:3]:
        if not part.isdigit():
            return None
        numbers.append(int(part))
    return tuple(numbers + [0] * (3 - len(numbers)))


def is_newer(tag):
    """True when ``tag`` is a release newer than the running version."""
    latest = _parse_version(tag)
    current = _parse_version(config.APP_VERSION)
    return latest is not None and current is not None and latest > current


def fetch_latest(timeout=_TIMEOUT):
    """Returns {"tag": str, "url": str} for the newest release, or None."""
    request = urllib.request.Request(
        RELEASES_URL,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"YearProgressWallpaper/{config.APP_VERSION}",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            data = json.load(response)
    except Exception as e:
        print(f"Update check failed: {e}")
        return None
    tag = data.get("tag_name")
    if not tag:
        return None
    return {"tag": tag, "url": data.get("html_url") or "https://github.com/HimanshuKumarSah/The_minimal_wallpaper/releases"}


def _stamp_check():
    try:
        settings = config.load_settings()
        settings["last_update_check"] = datetime.date.today().strftime("%Y-%m-%d")
        config.save_settings(settings)
    except Exception as e:
        print(f"Could not stamp update check: {e}")


def check():
    """Background check: returns the release dict when it's newer, else None.

    Skipped when the setting is off or when today's check already happened.
    (The manual UI button uses check_now(), which always fetches.)
    """
    settings = config.load_settings()
    if not settings.get("check_updates", True):
        return None
    today = datetime.date.today().strftime("%Y-%m-%d")
    if settings.get("last_update_check") == today:
        return None
    # Stamp before fetching so a network failure doesn't retry all day.
    _stamp_check()
    info = fetch_latest()
    if info and is_newer(info["tag"]):
        _latest["info"] = info
        return info
    return None


def check_and_notify(tray):
    """Launch-time background check: tray-notifies when a newer release exists.

    Shared by every app backend; network failures stay silent by design.
    """
    try:
        info = check()
        if info and tray:
            tray.notify(
                "Year Progress",
                f"Version {info['tag']} is available (you have {config.APP_VERSION}). "
                "See GitHub Releases to download it.",
            )
    except Exception as e:
        print(f"Update check error: {e}")


def check_now():
    """Manual UI check: always fetches, returns a display-ready dict."""
    info = fetch_latest()
    if not info:
        return {"error": "could not reach GitHub"}
    _stamp_check()
    newer = is_newer(info["tag"])
    if newer:
        _latest["info"] = info
    return {
        "tag": info["tag"],
        "url": info["url"],
        "newer": newer,
        "current": config.APP_VERSION,
    }


def cached():
    """Newest newer-than-current release seen this session (or None)."""
    return _latest["info"]
