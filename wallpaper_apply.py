"""Render-and-apply pipeline shared by every wallpaper trigger.

All call sites (tray, CLI ``--update-now``, webview bridge, Tk fallback,
startup scheduler) funnel through :func:`apply_wallpaper` so multi-monitor
rendering and per-display application stay consistent:

* single display (or ``multi_monitor`` off): the classic path — one render at
  the primary resolution, applied everywhere with the platform's native
  single-image API;
* multiple displays with ``multi_monitor`` on: one render per display sized to
  that display's pixels, applied through IDesktopWallpaper (Windows) or
  per-screen NSWorkspace calls (macOS).

The primary display always renders last with the default dated output name, so
the app's usual artifacts (``wallpaper_<date>.png``, preview thumbnail,
lock-screen source) keep working untouched.

Returns ``(ok, message, primary_png)``.
"""

import datetime
import os

import displays
import paths
import wallpaper_generator
import wallpaper_setter


def apply_wallpaper(settings):
    displays_list = displays.list_displays()
    multi = bool(settings.get("multi_monitor", True)) and len(displays_list) > 1

    if not multi:
        wall_path, _ = wallpaper_generator.generate_wallpaper(settings)
        png = os.path.splitext(wall_path)[0] + ".png"
        ok, msg = wallpaper_setter.set_wallpaper(png)
        return ok, msg, png

    stamp = datetime.date.today().strftime("%Y-%m-%d")
    data_dir = paths.data_dir()
    # Primary last: its render refreshes preview_thumbnail.png and the dated
    # wallpaper file the app treats as "today's wallpaper".
    ordered = sorted(displays_list, key=lambda d: d.primary)

    assignments = []
    primary_png = None
    for i, display in enumerate(ordered):
        output_path = None
        if not display.primary:
            output_path = os.path.join(data_dir, f"wallpaper_{stamp}_d{i}.bmp")
        wall_path, _ = wallpaper_generator.generate_wallpaper(
            settings,
            width=display.width,
            height=display.height,
            output_path=output_path,
        )
        png = os.path.splitext(wall_path)[0] + ".png"
        assignments.append((display.key, png))
        if display.primary:
            primary_png = png
    if primary_png is None:
        primary_png = assignments[0][1]

    ok, msg = wallpaper_setter.set_wallpapers(assignments, primary_png)
    return ok, msg, primary_png
