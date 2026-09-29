"""Display discovery for multi-monitor wallpaper generation.

A :class:`Display` carries just enough to render an image sized for that
screen: the platform token used to apply it (IDesktopWallpaper device path on
Windows, CGDirectDisplayID on macOS, None elsewhere), its pixel size, and
whether it is the primary display.

Single-display systems and platforms whose desktop environments only accept
one image for all outputs (Linux) collapse to a single entry, which keeps the
classic wallpaper path fully intact.
"""

import sys
from dataclasses import dataclass

import wallpaper_generator


@dataclass
class Display:
    key: object  # str monitor id (Windows/macOS) or None when unknown
    width: int
    height: int
    primary: bool


def list_displays():
    """Returns [Display] — never empty, never raises."""
    try:
        if sys.platform == "win32":
            displays = _windows_displays()
        elif sys.platform == "darwin":
            displays = _macos_displays()
        else:
            displays = _linux_displays()
        if displays:
            return displays
    except Exception as e:
        print(f"Display discovery failed ({e}); falling back to primary resolution.")
    w, h = wallpaper_generator.get_screen_resolution()
    return [Display(key=None, width=w, height=h, primary=True)]


def _windows_displays():
    import win_wallpaper_com

    monitors = win_wallpaper_com.enumerate_monitors()
    if not monitors:
        return []  # COM unavailable → caller falls back to the primary render
    return [
        Display(key=key, width=w, height=h, primary=primary)
        for key, w, h, primary in monitors
    ]


def _macos_displays():
    # NSScreen is the same enumeration the wallpaper setter iterates, so the
    # CG id in ``key`` maps 1:1 when applying; Quartz supplies retina pixels.
    import AppKit
    import Quartz

    screens = AppKit.NSScreen.screens()
    if not screens:
        return []
    displays = []
    for screen in screens:
        cg_id = int(screen.deviceDescription()["NSScreenNumber"])
        displays.append(
            Display(
                key=str(cg_id),
                width=Quartz.CGDisplayPixelsWide(cg_id),
                height=Quartz.CGDisplayPixelsHigh(cg_id),
                primary=bool(Quartz.CGDisplayIsMain(cg_id)),
            )
        )
    return displays


def _linux_displays():
    # gsettings/KDE/xfconf apply one image across all outputs, so a per-display
    # render would be wasted — size the single render to the primary display.
    w, h = wallpaper_generator.get_screen_resolution()
    return [Display(key=None, width=w, height=h, primary=True)]
