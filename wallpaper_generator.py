import ctypes
import datetime
import glob
import math
import os
import re
import shutil
import subprocess
import sys
import threading

from PIL import Image, ImageDraw, ImageFont

import config
import paths

FONTS_DIR = os.path.join(paths.resource_dir(), "assets", "fonts")

# Serializes all wallpaper/preview renders so concurrent triggers (tray click,
# midnight scheduler, Apply button) can never collide on the same files.
RENDER_LOCK = threading.Lock()

# Non-Windows probes shell out (xrandr/system_profiler), so their result is
# cached for the process lifetime. Windows re-probes on every call: ctypes is
# free and keeps up with monitor/DPI changes mid-session.
_RESOLUTION_CACHE = None

def get_screen_resolution():
    """Detect the primary monitor physical resolution (cross-platform)."""
    global _RESOLUTION_CACHE
    if _RESOLUTION_CACHE:
        return _RESOLUTION_CACHE
    if sys.platform == "win32":
        return _windows_resolution()
    w, h = _macos_resolution() if sys.platform == "darwin" else _linux_resolution()
    if w > 0 and h > 0:
        _RESOLUTION_CACHE = (w, h)
        return _RESOLUTION_CACHE
    return 2560, 1440


def _windows_resolution():
    try:
        user32 = ctypes.windll.user32
        user32.SetProcessDPIAware()
        w = user32.GetSystemMetrics(0)
        h = user32.GetSystemMetrics(1)
        if w > 0 and h > 0:
            return w, h
    except Exception as e:
        print(f"Error detecting resolution via ctypes: {e}")
    return 2560, 1440


def _macos_resolution():
    # 1) pyobjc CoreGraphics — pixel-exact (retina) and instant.
    try:
        import Quartz
        main = Quartz.CGMainDisplayID()
        w = Quartz.CGDisplayPixelsWide(main)
        h = Quartz.CGDisplayPixelsHigh(main)
        if w > 0 and h > 0:
            return w, h
    except Exception:
        pass
    # 2) system_profiler — always present but slow; the caller caches the result.
    try:
        proc = subprocess.run(
            ["system_profiler", "SPDisplaysDataType", "-json"],
            capture_output=True, text=True, timeout=25,
        )
        m = re.search(r'"(\d{3,5})\s*x\s*(\d{3,5})"', proc.stdout)
        if m:
            return int(m.group(1)), int(m.group(2))
    except Exception:
        pass
    # 3) Tk fallback — logical points, not retina pixels.
    return _tk_resolution()


def _linux_resolution():
    # xrandr (X11): fast and pixel-exact.
    if shutil.which("xrandr"):
        try:
            proc = subprocess.run(
                ["xrandr", "--current"], capture_output=True, text=True, timeout=5
            )
            if proc.returncode == 0:
                lines = proc.stdout.splitlines()
                line = next((ln for ln in lines if " connected primary " in ln), "")
                if not line:
                    line = next((ln for ln in lines if " connected " in ln), "")
                m = re.search(r"(\d+)x(\d+)\+\d+\+\d+", line)
                if m:
                    return int(m.group(1)), int(m.group(2))
        except Exception:
            pass
    # xdpyinfo (X11/XWayland): "dimensions:    2560x1440 pixels"
    if shutil.which("xdpyinfo"):
        try:
            proc = subprocess.run(
                ["xdpyinfo"], capture_output=True, text=True, timeout=5
            )
            m = re.search(r"dimensions:\s*(\d+)x(\d+)", proc.stdout)
            if m:
                return int(m.group(1)), int(m.group(2))
        except Exception:
            pass
    # Headless (CI, Wayland without tools): caller falls back to 2560x1440.
    return _tk_resolution()


def _tk_resolution():
    """Last resort: ask Tk, reusing an existing root when one is alive."""
    try:
        import tkinter as tk
        root = getattr(tk, "_default_root", None)
        if root is not None:
            return root.winfo_screenwidth(), root.winfo_screenheight()
        root = tk.Tk()
        root.withdraw()
        try:
            return root.winfo_screenwidth(), root.winfo_screenheight()
        finally:
            root.destroy()
    except Exception:
        return 0, 0

def requires_daily_update(settings):
    """
    True when today's wallpaper has not been rendered yet (stale or missing),
    used to decide whether a launch-time / midnight update is needed.

    The files on disk are the source of truth: a stale last_rendered_date stamp
    (e.g. written by an older settings.json loaded before the stamp was
    updated) must not force a pointless re-render every launch.
    """
    today = datetime.date.today().strftime("%Y-%m-%d")
    png_path = os.path.join(paths.data_dir(), f"wallpaper_{today}.png")
    bmp_path = os.path.join(paths.data_dir(), f"wallpaper_{today}.bmp")
    if os.path.exists(png_path) or os.path.exists(bmp_path):
        return False
    if settings.get("last_rendered_date") == today:
        # Stamp says today but the files are gone (deleted or failed write):
        # fall back to legacy pre-dated files for older installs.
        legacy_png = os.path.join(paths.data_dir(), "wallpaper_current.png")
        legacy_bmp = os.path.join(paths.data_dir(), "wallpaper_current.bmp")
        return not (os.path.exists(legacy_png) or os.path.exists(legacy_bmp))
    return True


def current_wallpaper_path():
    """Returns the path of today's applied PNG wallpaper, or the most recent
    dated wallpaper if today's hasn't been generated yet (None if none exist)."""
    today = datetime.date.today().strftime("%Y-%m-%d")
    png = os.path.join(paths.data_dir(), f"wallpaper_{today}.png")
    if os.path.exists(png):
        return png
    candidates = sorted(
        glob.glob(os.path.join(paths.data_dir(), "wallpaper_*.png")), reverse=True
    )
    return candidates[0] if candidates else None


def _cleanup_old_wallpapers(keep_png):
    """
    Deletes wallpapers from previous days so only the current day's files
    remain on disk (the .png/.bmp pair for keep_png). Also removes legacy
    wallpaper_current.* leftovers. Files outside data_dir are never touched.
    """
    data_dir = paths.data_dir()
    keep_png = os.path.abspath(keep_png)
    if os.path.dirname(os.path.normcase(keep_png)) != os.path.normcase(os.path.abspath(data_dir)):
        return
    keep_stem = os.path.splitext(os.path.normcase(keep_png))[0]
    # Multi-monitor renders produce wallpaper_<date>_dN variants; they share the
    # base dated stem, which must keep the whole set (including the primary
    # wallpaper_*.png) alive across per-display renders of the same day.
    base_stem = re.sub(r"_d\d+$", "", keep_stem)
    keep = {os.path.normcase(keep_png), keep_stem + ".bmp"}
    patterns = glob.glob(os.path.join(data_dir, "wallpaper_*.png")) + \
               glob.glob(os.path.join(data_dir, "wallpaper_*.bmp"))
    for p in patterns:
        np = os.path.normcase(p)
        stem = os.path.splitext(np)[0]
        suffix = stem[len(base_stem):] if stem.startswith(base_stem) else None
        same_day = (
            stem == base_stem
            or (suffix is not None and suffix.startswith("_d") and suffix[2:].isdigit())
        )
        if np in keep or same_day:
            continue
        try:
            os.remove(p)
        except OSError:
            pass
    for legacy in ("wallpaper_current.png", "wallpaper_current.bmp"):
        p = os.path.join(data_dir, legacy)
        if os.path.normcase(os.path.abspath(p)) in keep:
            continue
        try:
            if os.path.exists(p):
                os.remove(p)
        except OSError:
            pass

def hex_to_rgb(hex_str, default=(255, 255, 255)):
    """Convert hex string (#RRGGBB) to RGB tuple."""
    if not hex_str:
        return default
    try:
        cleaned = hex_str.strip().lstrip("#")
        if len(cleaned) == 6:
            return tuple(int(cleaned[i:i+2], 16) for i in (0, 2, 4))
        elif len(cleaned) == 3:
            return tuple(int(cleaned[i]*2, 16) for i in range(3))
    except Exception:
        pass
    return default

# (face, size, bold) -> (font, source_path, source_mtime). Every render
# requests the same eight fonts; re-parsing the TTF each time was pure I/O.
_font_cache = {}


def load_custom_font(font_face, size, bold=False):
    """
    Loads aesthetic modern fonts (Outfit, Montserrat, Inter, Cinzel, Bahnschrift)
    with graceful fallbacks.

    Cached by (face, size, bold) and validated against the source file's mtime,
    so an edited/replaced font file is picked up without a restart.
    """
    size_int = max(8, int(size))
    face = str(font_face).lower().strip()
    key = (face, size_int, bold)

    cached = _font_cache.get(key)
    if cached is not None:
        font, cpath, cmtime = cached
        if cpath is None:
            return font
        try:
            if os.path.getmtime(cpath) == cmtime:
                return font
        except OSError:
            pass

    font, chosen = _load_custom_font_uncached(face, size_int, bold)
    if chosen:
        try:
            mtime = os.path.getmtime(chosen)
        except OSError:
            chosen, mtime = None, None
        _font_cache[key] = (font, chosen, mtime)
    else:
        _font_cache[key] = (font, None, None)
    return font


def _load_custom_font_uncached(face, size_int, bold):
    """Font resolution proper; returns ``(font, source_path_or_None)``."""
    paths_to_try = []
    
    if face == "outfit":
        paths_to_try = [
            os.path.join(FONTS_DIR, "Outfit-Variable.ttf"),
            "C:/Windows/Fonts/Montserrat-Bold.ttf" if bold else "C:/Windows/Fonts/Montserrat-Medium.ttf",
            "C:/Windows/Fonts/bahnschrift.ttf"
        ]
    elif face == "montserrat":
        paths_to_try = [
            "C:/Windows/Fonts/Montserrat-Bold.ttf" if bold else "C:/Windows/Fonts/Montserrat-Medium.ttf",
            "C:/Windows/Fonts/Montserrat-Regular.ttf",
            os.path.join(FONTS_DIR, "Outfit-Variable.ttf"),
            "C:/Windows/Fonts/bahnschrift.ttf"
        ]
    elif face == "inter":
        paths_to_try = [
            os.path.join(FONTS_DIR, "Inter-Variable.ttf"),
            os.path.join(FONTS_DIR, "Outfit-Variable.ttf"),
            "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf"
        ]
    elif face == "cinzel":
        paths_to_try = [
            os.path.join(FONTS_DIR, "Cinzel-Variable.ttf"),
            "C:/Windows/Fonts/georgiab.ttf" if bold else "C:/Windows/Fonts/georgia.ttf",
            "C:/Windows/Fonts/constantia.ttf"
        ]
    elif face == "bahnschrift":
        paths_to_try = [
            "C:/Windows/Fonts/bahnschrift.ttf",
            os.path.join(FONTS_DIR, "Outfit-Variable.ttf")
        ]
    else:  # default to outfit
        paths_to_try = [
            os.path.join(FONTS_DIR, "Outfit-Variable.ttf"),
            "C:/Windows/Fonts/Montserrat-Bold.ttf",
            "C:/Windows/Fonts/bahnschrift.ttf"
        ]
        
    for p in paths_to_try:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size_int), p
            except Exception:
                continue
                
    # Ultimate fallbacks: bundled fonts first, then OS system fonts
    for fb in _system_font_fallbacks(bold):
        if os.path.exists(fb):
            try:
                return ImageFont.truetype(fb, size_int), fb
            except Exception:
                pass
                
    return ImageFont.load_default(), None


def _system_font_fallbacks(bold):
    """Common system fonts per OS, tried after the bundled fonts.

    The Windows entries come first so Windows behaviour stays identical to
    previous releases; macOS/Linux only reach them when the bundled fonts
    are missing from the package.
    """
    windows = [
        "C:/Windows/Fonts/segoeuib.ttf" if bold else "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    macos = [
        "/System/Library/Fonts/Helvetica.ttc",
        "/Library/Fonts/Arial.ttf",
    ]
    linux = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
        if bold
        else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    return windows + macos + linux

def wrap_text(text, font, max_width, draw):
    """Word wrap text to fit within a given pixel width."""
    words = text.split()
    if not words:
        return []
    lines = []
    current_line = words[0]
    for word in words[1:]:
        test_line = f"{current_line} {word}"
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    lines.append(current_line)
    return lines

def get_active_quote(settings):
    """Determine quote text and author based on active settings."""
    mode = settings.get("quote_mode", "preset")
    quotes_list = config.load_quotes()
    if not quotes_list:
        quotes_list = [{"text": "Make each day your masterpiece.", "author": "John Wooden"}]
    
    if mode == "custom":
        q_text = settings.get("custom_quote", "Make each day your masterpiece.")
        q_author = settings.get("custom_author", "John Wooden")
        return q_text.strip(), q_author.strip()
    
    elif mode == "daily_random":
        today = datetime.date.today()
        day_of_year = today.timetuple().tm_yday
        idx = (day_of_year + settings.get("daily_seed", 0)) % len(quotes_list)
        q = quotes_list[idx]
        return q["text"], q["author"]
        
    else:  # preset
        idx = settings.get("preset_index", 0)
        if 0 <= idx < len(quotes_list):
            q = quotes_list[idx]
        else:
            q = quotes_list[0]
        return q["text"], q["author"]

def _one_off_target(y, m, d):
    """A one-off countdown date, or None when the calendar date is invalid."""
    try:
        return datetime.date(y, m, d)
    except ValueError:
        return None


def _yearly_target(year, m, d):
    """The yearly recurrence in `year`. Feb 29 in a non-leap year rolls forward
    to Mar 1 (same roll-forward the web UI / Windows date pickers perform)
    instead of vanishing for the whole year."""
    try:
        return datetime.date(year, m, d)
    except ValueError:
        if (m, d) == (2, 29):
            try:
                return datetime.date(year, 3, 1)
            except ValueError:
                return None
        return None


def get_active_countdown(settings, today=None):
    """
    Resolves the selected countdown target into display-ready data.
    Returns {"label", "date", "days", "text"} or None when there is nothing
    valid to show (no targets, bad data, or a passed one-off date).
    """
    if not settings.get("show_countdown", True):
        return None
    targets = settings.get("countdown_targets") or []
    if not targets:
        return None
    try:
        idx = int(settings.get("countdown_index", 0) or 0)
    except (TypeError, ValueError):
        idx = 0
    if not (0 <= idx < len(targets)):
        return None

    t = targets[idx] or {}
    label = str(t.get("label") or "").strip()
    date_str = str(t.get("date") or "").strip()
    if not label or len(date_str) != 10:
        return None

    today = today or datetime.date.today()
    try:
        y, m, d = (int(part) for part in date_str.split("-"))
        if t.get("yearly"):
            target = _yearly_target(today.year, m, d)
            if target is None:
                return None
            if target < today:
                target = _yearly_target(today.year + 1, m, d)
                if target is None:
                    return None
        else:
            target = _one_off_target(y, m, d)
            if target is None:
                return None
    except ValueError:
        return None

    days = (target - today).days
    if days < 0:
        return None

    upper = label.upper()
    if days == 0:
        text = f"{upper} IS TODAY"
    elif days == 1:
        text = f"1 DAY UNTIL {upper}"
    else:
        text = f"{days} DAYS UNTIL {upper}"

    return {"label": label, "date": target.isoformat(), "days": days, "text": text}


def generate_wallpaper(settings, target_date=None, width=None, height=None, output_path=None,
                       preview_path=None, preview_only=False, cleanup=True):
    """Thread-safe wrapper that serializes concurrent render requests."""
    with RENDER_LOCK:
        return _generate_wallpaper_impl(
            settings,
            target_date=target_date,
            width=width,
            height=height,
            output_path=output_path,
            preview_path=preview_path,
            preview_only=preview_only,
            cleanup=cleanup,
        )


def _generate_wallpaper_impl(settings, target_date=None, width=None, height=None, output_path=None, preview_path=None, preview_only=False, cleanup=True):
    """
    Renders the wallpaper image with premium typography, customizable colors, and zoom scaling.
    If preview_only=True, renders quickly at preview scale without disk thrashing.
    """
    if width is None or height is None:
        width, height = get_screen_resolution()
        
    if target_date is None:
        target_date = datetime.date.today()
        
    year = target_date.year
    day_of_year = target_date.timetuple().tm_yday
    is_leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
    total_days = 366 if is_leap else 365
    days_left = max(0, total_days - day_of_year)
    pct = (day_of_year / total_days) * 100.0
    
    # 2x supersampling for final wallpaper, 0.5x for rapid live GUI preview
    scale = 0.5 if preview_only else 2
    sw, sh = int(width * scale), int(height * scale)
    
    # Color palette
    c_bg = hex_to_rgb(settings.get("color_bg", "#070709"), (7, 7, 9))
    c_passed = hex_to_rgb(settings.get("color_passed", "#FFFFFF"), (255, 255, 255))
    c_current = hex_to_rgb(settings.get("color_current", "#FFFFFF"), (255, 255, 255))
    c_coming = hex_to_rgb(settings.get("color_coming", "#2D2E38"), (45, 46, 56))
    c_text_pri = hex_to_rgb(settings.get("color_text_primary", "#FFFFFF"), (255, 255, 255))
    c_text_sec = hex_to_rgb(settings.get("color_text_secondary", "#9CA3AF"), (156, 163, 175))
    
    # Progress ring track
    c_track = (
        max(18, int(c_coming[0] * 0.7)),
        max(18, int(c_coming[1] * 0.7)),
        max(22, int(c_coming[2] * 0.7))
    )
    
    img = Image.new("RGB", (sw, sh), c_bg)
    draw = ImageDraw.Draw(img)
    
    # Layout selection
    layout = settings.get("layout", "ref_10")
    if layout == "ref_10":
        cols = 10
    elif layout == "balanced_20":
        cols = 20
    elif layout == "matrix_25":
        cols = 25
    elif layout == "calendar_53":
        cols = 53
    else:
        cols = 10
        
    rows = math.ceil(total_days / cols)
    
    # Zoom scaling factor (user can zoom grid in/out)
    grid_zoom = float(settings.get("grid_zoom", 1.0))
    grid_zoom = max(0.4, min(2.5, grid_zoom))
    
    # Base resolution factor relative to 1440p
    res_factor = min(width / 2560.0, height / 1440.0)
    res_factor = max(0.65, min(1.6, res_factor))
    
    # Vertical budget: the layout is centered with a minimum margin top and
    # bottom. Every metric below scales with res_factor, so if the stacked
    # content would run past the bottom edge (small screens, high grid zoom)
    # we shrink res_factor and recompute until everything fits.
    top_margin = int(35 * scale)
    available_h = sh - 2 * top_margin

    for _ in range(3):
        # Calculate spacing and dot sizes with zoom
        if cols == 10:
            base_spacing = 22
            base_passed = 6.8
            base_coming = 3.2
        elif cols == 20:
            base_spacing = 28
            base_passed = 7.5
            base_coming = 3.6
        elif cols == 25:
            base_spacing = 26
            base_passed = 7.0
            base_coming = 3.4
        else:  # calendar_53
            base_spacing = 18
            base_passed = 5.5
            base_coming = 2.8
        
        cell_spacing = int(base_spacing * res_factor * scale * grid_zoom)
        passed_r = max(2, int(base_passed * res_factor * scale * grid_zoom))
        coming_r = max(1, int(base_coming * res_factor * scale * grid_zoom))
    
        grid_w = (cols - 1) * cell_spacing
        grid_h = (rows - 1) * cell_spacing
    
        # Selected font face
        font_face = settings.get("font_face", "outfit")
    
        font_date = load_custom_font(font_face, 16 * res_factor * scale, bold=False)
        font_year = load_custom_font(font_face, 54 * res_factor * scale, bold=True)
        font_pct = load_custom_font(font_face, 24 * res_factor * scale, bold=True)
        font_sub = load_custom_font(font_face, 12 * res_factor * scale, bold=False)
        font_days_left = load_custom_font(font_face, 16 * res_factor * scale, bold=True)
        font_quote = load_custom_font(font_face, 19 * res_factor * scale, bold=False)
        font_author = load_custom_font(font_face, 14 * res_factor * scale, bold=False)
        font_countdown = load_custom_font(font_face, 15 * res_factor * scale, bold=True)

        show_ring = settings.get("show_progress_ring", True)
        show_days_left = settings.get("show_days_left", True)
        show_quote = settings.get("show_quote", True)
        show_countdown = settings.get("show_countdown", True)
    
        ring_radius = int(50 * res_factor * scale)
        ring_stroke = int(5.5 * res_factor * scale)
    
        # Quote text
        quote_lines = []
        author_text = ""
        if show_quote:
            q_text, q_author = get_active_quote(settings)
            if q_text:
                max_quote_w = int(width * 0.70 * scale)
                quote_formatted = f'"{q_text}"'
                quote_lines = wrap_text(quote_formatted, font_quote, max_quote_w, draw)
                if q_author:
                    author_text = f"— {q_author}"

        # Countdown banner ("N DAYS UNTIL <LABEL>")
        countdown_lines = []
        if show_countdown:
            countdown = get_active_countdown(settings, target_date)
            if countdown:
                max_countdown_w = int(width * 0.60 * scale)
                countdown_lines = wrap_text(countdown["text"], font_countdown, max_countdown_w, draw)

        # Calculate vertical heights to center the layout
        date_h = int(28 * res_factor * scale)
        year_h = int(60 * res_factor * scale)
        ring_total_h = (ring_radius * 2 + int(26 * res_factor * scale)) if show_ring else 0
        days_left_h = int(42 * res_factor * scale) if show_days_left else 0
        countdown_line_h = int(30 * res_factor * scale)
        countdown_total_h = (len(countdown_lines) * countdown_line_h) if countdown_lines else 0
        grid_gap_top = int(30 * res_factor * scale)
        grid_gap_bottom = int(36 * res_factor * scale)

        quote_line_h = int(27 * res_factor * scale)
        author_budget = 0
        if show_quote and quote_lines and author_text:
            a_bbox = font_author.getbbox(author_text)
            author_budget = (a_bbox[3] - a_bbox[1]) + int(6 * scale)
        quote_total_h = (len(quote_lines) * quote_line_h + author_budget) if (show_quote and quote_lines) else 0

        total_content_h = (
            date_h + 
            year_h + 
            ring_total_h + 
            days_left_h + 
            countdown_total_h + 
            grid_gap_top + 
            grid_h + 
            grid_gap_bottom + 
            quote_total_h
        )

        # Dots overhang their grid cell and the author line sits below its
        # budgeted block, so budget the overhang on both sides.
        dot_overhang = passed_r + max(2, int(3.2 * scale * grid_zoom)) + int(2 * scale)
        if available_h <= 0 or total_content_h + 2 * dot_overhang <= available_h:
            break
        res_factor *= available_h / float(total_content_h + 2 * dot_overhang)
    
    # Center vertically
    curr_y = max(top_margin, (sh - total_content_h) // 2)
    cx = sw // 2
    
    # 1. Date (e.g. S E P T E M B E R   2 1)
    date_str = target_date.strftime("%B %d").upper()
    spaced_date = "  ".join(list(date_str))
    bbox = font_date.getbbox(spaced_date)
    w_d = bbox[2] - bbox[0]
    draw.text((cx - w_d // 2, curr_y), spaced_date, font=font_date, fill=c_text_sec)
    curr_y += date_h
    
    # 2. Year (2026)
    year_str = str(year)
    bbox = font_year.getbbox(year_str)
    w_y = bbox[2] - bbox[0]
    draw.text((cx - w_y // 2, curr_y), year_str, font=font_year, fill=c_text_pri)
    curr_y += year_h
    
    # 3. Progress Ring
    if show_ring:
        ring_box = [cx - ring_radius, curr_y, cx + ring_radius, curr_y + ring_radius * 2]
        # Background ring
        draw.ellipse(ring_box, outline=c_track, width=ring_stroke)
        # White / accent progress arc: starts at top (-90 deg)
        angle_end = -90 + (pct / 100.0) * 360
        draw.arc(ring_box, start=-90, end=angle_end, fill=c_passed, width=ring_stroke)
        
        # Text inside ring
        pct_text = f"{pct:.1f}%"
        p_bbox = font_pct.getbbox(pct_text)
        pw = p_bbox[2] - p_bbox[0]
        ph = p_bbox[3] - p_bbox[1]
        
        sub_text = "passed"
        s_bbox = font_sub.getbbox(sub_text)
        sw_t = s_bbox[2] - s_bbox[0]
        
        ring_cy = curr_y + ring_radius
        draw.text((cx - pw // 2, ring_cy - ph - int(2 * scale)), pct_text, font=font_pct, fill=c_text_pri)
        draw.text((cx - sw_t // 2, ring_cy + int(6 * scale)), sub_text, font=font_sub, fill=c_text_sec)
        curr_y += ring_radius * 2 + int(26 * res_factor * scale)
        
    # 4. Days Left Banner
    if show_days_left:
        days_text = f"{days_left} DAYS LEFT IN {year}"
        d_bbox = font_days_left.getbbox(days_text)
        dw = d_bbox[2] - d_bbox[0]
        draw.text((cx - dw // 2, curr_y), days_text, font=font_days_left, fill=c_text_pri)
        curr_y += days_left_h

    # 4b. Countdown banner
    for line in countdown_lines:
        c_bbox = font_countdown.getbbox(line)
        cw = c_bbox[2] - c_bbox[0]
        draw.text((cx - cw // 2, curr_y), line, font=font_countdown, fill=c_text_sec)
        curr_y += countdown_line_h

    curr_y += grid_gap_top
    
    # 5. Dot Grid
    gx_start = cx - grid_w // 2
    day_idx = 1
    
    for r in range(rows):
        for c in range(cols):
            if day_idx > total_days:
                break
            dot_x = gx_start + c * cell_spacing
            dot_y = curr_y + r * cell_spacing
            
            if day_idx < day_of_year:
                # Passed days: bigger circle in c_passed color
                draw.ellipse([dot_x - passed_r, dot_y - passed_r, dot_x + passed_r, dot_y + passed_r], fill=c_passed)
            elif day_idx == day_of_year:
                # Current day: bigger circle in c_current + outer accent ring
                draw.ellipse([dot_x - passed_r, dot_y - passed_r, dot_x + passed_r, dot_y + passed_r], fill=c_current)
                if settings.get("highlight_current_day", True):
                    ring_gap = max(2, int(3.2 * scale * grid_zoom))
                    draw.ellipse([
                        dot_x - passed_r - ring_gap, dot_y - passed_r - ring_gap,
                        dot_x + passed_r + ring_gap, dot_y + passed_r + ring_gap
                    ], outline=c_current, width=max(1, int(1.6 * scale * grid_zoom)))
            else:
                # Coming days: smaller, greyed out in c_coming color
                draw.ellipse([dot_x - coming_r, dot_y - coming_r, dot_x + coming_r, dot_y + coming_r], fill=c_coming)
            day_idx += 1
            
    curr_y += grid_h + grid_gap_bottom
    
    # 6. Motivational quote
    if show_quote and quote_lines:
        for line in quote_lines:
            q_bbox = font_quote.getbbox(line)
            qw = q_bbox[2] - q_bbox[0]
            draw.text((cx - qw // 2, curr_y), line, font=font_quote, fill=c_text_pri)
            curr_y += quote_line_h
            
        if author_text:
            curr_y += int(6 * scale)
            a_bbox = font_author.getbbox(author_text)
            aw = a_bbox[2] - a_bbox[0]
            draw.text((cx - aw // 2, curr_y), author_text, font=font_author, fill=c_text_sec)
            
    if preview_only:
        if preview_path is None:
            preview_path = os.path.join(paths.data_dir(), "preview_thumbnail.png")
        img.save(preview_path, "PNG")
        return None, preview_path

    # Resample to native display resolution using Lanczos
    res = img.resize((width, height), Image.Resampling.LANCZOS)

    # Save wallpaper file under a date-stamped name so previous days' wallpapers
    # can be identified and cleaned up afterwards.
    if output_path is None:
        stamp = target_date.strftime("%Y-%m-%d")
        output_path = os.path.join(paths.data_dir(), f"wallpaper_{stamp}.bmp")
    
    res.save(output_path, "BMP")
    
    # Also save PNG copy
    png_path = os.path.splitext(output_path)[0] + ".png"
    res.save(png_path, "PNG")
    
    # Delete previous days' wallpaper files (keep only today's). Callers that
    # render several displays in a row pass cleanup=False on every render but
    # the last — the glob/delete scan would otherwise repeat per display.
    if cleanup:
        _cleanup_old_wallpapers(png_path)
    
    # Save scaled preview for GUI
    if preview_path is None:
        preview_path = os.path.join(paths.data_dir(), "preview_thumbnail.png")
    
    preview_w = 640
    preview_h = int(height * (preview_w / width))
    thumb = res.resize((preview_w, preview_h), Image.Resampling.LANCZOS)
    thumb.save(preview_path, "PNG")
    
    return output_path, preview_path

if __name__ == "__main__":
    settings = config.load_settings()
    wall_path, prev_path = generate_wallpaper(settings)
    print(f"Wallpaper generated: {wall_path}")
