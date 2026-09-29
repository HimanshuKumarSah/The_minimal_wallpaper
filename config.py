import datetime
import json
import os
import shutil
import threading

import paths

SETTINGS_FILE = os.path.join(paths.data_dir(), "settings.json")
QUOTES_FILE = os.path.join(paths.data_dir(), "quotes.json")

# Shown in the UI and sent as the User-Agent of update checks; bump with each
# release (the GitHub tag the updater compares against is "v" + this).
APP_VERSION = "1.1.0"

# Serializes read-modify-write cycles on settings.json (tray / scheduler / UI
# threads all touch it), so a stale in-memory dict can't silently clobber a
# value another thread just stamped.
_settings_lock = threading.RLock()

FONT_PRESETS = {
    "outfit": "Outfit (Modern Geometric)",
    "montserrat": "Montserrat (Architectural)",
    "inter": "Inter (Ultra-Clean Technical)",
    "cinzel": "Cinzel (Stoic Classical)",
    "bahnschrift": "Bahnschrift (DIN Engineering)"
}

COLOR_THEMES = {
    "noir": {
        "name": "Monochrome Noir",
        "color_bg": "#070709",
        "color_passed": "#FFFFFF",
        "color_current": "#FFFFFF",
        "color_coming": "#2D2E38",
        "color_text_primary": "#FFFFFF",
        "color_text_secondary": "#9CA3AF",
        "ui_canvas": "#1A1C20",
        "ui_bars": "#15171B",
        "ui_panel": "#22252C",
        "ui_panel_alt": "#1D2026",
        "ui_input": "#2A2E37",
        "ui_hover": "#363A45",
        "ui_border": "#363A45",
        "ui_accent": "#FFFFFF",
        "ui_text_sec": "#C7CBD4"
    },
    "pure_black": {
        "name": "Pure Black OLED",
        "color_bg": "#000000",
        "color_passed": "#F4F4F6",
        "color_current": "#FFFFFF",
        "color_coming": "#222228",
        "color_text_primary": "#F4F4F6",
        "color_text_secondary": "#8A8A93",
        "ui_canvas": "#111113",
        "ui_bars": "#0B0B0D",
        "ui_panel": "#19191C",
        "ui_panel_alt": "#151517",
        "ui_input": "#222226",
        "ui_hover": "#2D2D33",
        "ui_border": "#2B2B30",
        "ui_accent": "#FFFFFF",
        "ui_text_sec": "#B4B4BC"
    },
    "midnight": {
        "name": "Cyber Midnight",
        "color_bg": "#090D16",
        "color_passed": "#38BDF8",
        "color_current": "#67E8F9",
        "color_coming": "#1E293B",
        "color_text_primary": "#F0F9FF",
        "color_text_secondary": "#7DD3FC",
        "ui_canvas": "#101622",
        "ui_bars": "#0C111B",
        "ui_panel": "#182030",
        "ui_panel_alt": "#141B28",
        "ui_input": "#222D42",
        "ui_hover": "#2C3953",
        "ui_border": "#28354D",
        "ui_accent": "#38BDF8",
        "ui_text_sec": "#BAE6FD"
    },
    "emerald": {
        "name": "Emerald Zen",
        "color_bg": "#06120C",
        "color_passed": "#34D399",
        "color_current": "#A7F3D0",
        "color_coming": "#152B1E",
        "color_text_primary": "#ECFDF5",
        "color_text_secondary": "#6EE7B7",
        "ui_canvas": "#101B15",
        "ui_bars": "#0C1510",
        "ui_panel": "#17271F",
        "ui_panel_alt": "#13211A",
        "ui_input": "#20352A",
        "ui_hover": "#2A4537",
        "ui_border": "#274033",
        "ui_accent": "#34D399",
        "ui_text_sec": "#A7F3D0"
    },
    "gold": {
        "name": "Golden Hour",
        "color_bg": "#12100C",
        "color_passed": "#FBBF24",
        "color_current": "#FDE68A",
        "color_coming": "#2A231B",
        "color_text_primary": "#FFFBEB",
        "color_text_secondary": "#FCD34D",
        "ui_canvas": "#1D1914",
        "ui_bars": "#171410",
        "ui_panel": "#29241D",
        "ui_panel_alt": "#221E18",
        "ui_input": "#383127",
        "ui_hover": "#463E32",
        "ui_border": "#433A2E",
        "ui_accent": "#FBBF24",
        "ui_text_sec": "#FDE68A"
    },
    "crimson": {
        "name": "Solar Crimson",
        "color_bg": "#10090C",
        "color_passed": "#FB7185",
        "color_current": "#FDA4AF",
        "color_coming": "#2C1721",
        "color_text_primary": "#FFF1F2",
        "color_text_secondary": "#F472B6",
        "ui_canvas": "#1B1216",
        "ui_bars": "#160E12",
        "ui_panel": "#261920",
        "ui_panel_alt": "#20151B",
        "ui_input": "#35232C",
        "ui_hover": "#442D39",
        "ui_border": "#412B37",
        "ui_accent": "#FB7185",
        "ui_text_sec": "#FDA4AF"
    },
    "amethyst": {
        "name": "Royal Amethyst",
        "color_bg": "#0D0814",
        "color_passed": "#C084FC",
        "color_current": "#E9D5FF",
        "color_coming": "#231833",
        "color_text_primary": "#FAF5FF",
        "color_text_secondary": "#D8B4FE",
        "ui_canvas": "#171220",
        "ui_bars": "#120E1A",
        "ui_panel": "#211A2E",
        "ui_panel_alt": "#1B1526",
        "ui_input": "#2D243F",
        "ui_hover": "#3B2F52",
        "ui_border": "#392D50",
        "ui_accent": "#C084FC",
        "ui_text_sec": "#E9D5FF"
    },
    "nordic_frost": {
        "name": "Nordic Frost",
        "color_bg": "#0B1117",
        "color_passed": "#7DD3FC",
        "color_current": "#BAE6FD",
        "color_coming": "#1E293B",
        "color_text_primary": "#F0F9FF",
        "color_text_secondary": "#94A3B8",
        "ui_canvas": "#121A23",
        "ui_bars": "#0E151C",
        "ui_panel": "#192431",
        "ui_panel_alt": "#151F2A",
        "ui_input": "#223143",
        "ui_hover": "#2C3F56",
        "ui_border": "#2A3C52",
        "ui_accent": "#7DD3FC",
        "ui_text_sec": "#BAE6FD"
    },
    "matcha": {
        "name": "Matcha Minimal",
        "color_bg": "#0E1410",
        "color_passed": "#86EFAC",
        "color_current": "#BBF7D0",
        "color_coming": "#1F2E23",
        "color_text_primary": "#F0FDF4",
        "color_text_secondary": "#86EFAC",
        "ui_canvas": "#141C16",
        "ui_bars": "#101712",
        "ui_panel": "#1C2720",
        "ui_panel_alt": "#17211A",
        "ui_input": "#25342B",
        "ui_hover": "#304337",
        "ui_border": "#2E4135",
        "ui_accent": "#86EFAC",
        "ui_text_sec": "#BBF7D0"
    },
    "terracotta": {
        "name": "Desert Terracotta",
        "color_bg": "#150F0D",
        "color_passed": "#FB923C",
        "color_current": "#FDBA74",
        "color_coming": "#2E1E18",
        "color_text_primary": "#FFF7ED",
        "color_text_secondary": "#FDBA74",
        "ui_canvas": "#1D1614",
        "ui_bars": "#171110",
        "ui_panel": "#281F1C",
        "ui_panel_alt": "#221A17",
        "ui_input": "#372A26",
        "ui_hover": "#463631",
        "ui_border": "#433430",
        "ui_accent": "#FB923C",
        "ui_text_sec": "#FDBA74"
    },
    "ocean_abyss": {
        "name": "Ocean Abyss",
        "color_bg": "#061017",
        "color_passed": "#2DD4BF",
        "color_current": "#5EEAD4",
        "color_coming": "#112833",
        "color_text_primary": "#F0FDFA",
        "color_text_secondary": "#5EEAD4",
        "ui_canvas": "#0F1922",
        "ui_bars": "#0B141C",
        "ui_panel": "#162330",
        "ui_panel_alt": "#121E2A",
        "ui_input": "#1F3142",
        "ui_hover": "#294157",
        "ui_border": "#273D53",
        "ui_accent": "#2DD4BF",
        "ui_text_sec": "#5EEAD4"
    },
    "sepia": {
        "name": "Memento Mori Sepia",
        "color_bg": "#12100E",
        "color_passed": "#E2D8CE",
        "color_current": "#FFFFFF",
        "color_coming": "#2D2823",
        "color_text_primary": "#FAF5EF",
        "color_text_secondary": "#B8AFA6",
        "ui_canvas": "#1B1917",
        "ui_bars": "#151312",
        "ui_panel": "#262320",
        "ui_panel_alt": "#201E1B",
        "ui_input": "#34302C",
        "ui_hover": "#423E39",
        "ui_border": "#3E3A35",
        "ui_accent": "#E2D8CE",
        "ui_text_sec": "#D1C7BD"
    },
    "tokyo_rain": {
        "name": "Tokyo Rain",
        "color_bg": "#0A0D14",
        "color_passed": "#818CF8",
        "color_current": "#A5B4FC",
        "color_coming": "#1B2033",
        "color_text_primary": "#EEF2FF",
        "color_text_secondary": "#A5B4FC",
        "ui_canvas": "#131622",
        "ui_bars": "#0F111B",
        "ui_panel": "#1B2031",
        "ui_panel_alt": "#161B29",
        "ui_input": "#252B42",
        "ui_hover": "#303754",
        "ui_border": "#2E3652",
        "ui_accent": "#818CF8",
        "ui_text_sec": "#A5B4FC"
    },
    "rose_quartz": {
        "name": "Rose Quartz",
        "color_bg": "#120E12",
        "color_passed": "#F472B6",
        "color_current": "#FBCFE8",
        "color_coming": "#2A1E29",
        "color_text_primary": "#FDF2F8",
        "color_text_secondary": "#F472B6",
        "ui_canvas": "#1C151C",
        "ui_bars": "#161016",
        "ui_panel": "#261D26",
        "ui_panel_alt": "#211821",
        "ui_input": "#362936",
        "ui_hover": "#453445",
        "ui_border": "#433343",
        "ui_accent": "#F472B6",
        "ui_text_sec": "#FBCFE8"
    },
    "titanium": {
        "name": "Titanium Studio",
        "color_bg": "#101114",
        "color_passed": "#E2E8F0",
        "color_current": "#FFFFFF",
        "color_coming": "#272A32",
        "color_text_primary": "#F8FAFC",
        "color_text_secondary": "#94A3B8",
        "ui_canvas": "#181A20",
        "ui_bars": "#14151B",
        "ui_panel": "#21242D",
        "ui_panel_alt": "#1C1E26",
        "ui_input": "#2C303B",
        "ui_hover": "#383D4C",
        "ui_border": "#363B49",
        "ui_accent": "#E2E8F0",
        "ui_text_sec": "#CBD5E1"
    },
    "nord": {
        "name": "Nordic Frostbite",
        "color_bg": "#20242C",
        "color_passed": "#88C0D0",
        "color_current": "#ECEFF4",
        "color_coming": "#353C4A",
        "color_text_primary": "#ECEFF4",
        "color_text_secondary": "#81A1C1",
        "ui_canvas": "#2E3440",
        "ui_bars": "#242933",
        "ui_panel": "#3B4252",
        "ui_panel_alt": "#333A48",
        "ui_input": "#434C5E",
        "ui_hover": "#4C566A",
        "ui_border": "#4C566A",
        "ui_accent": "#88C0D0",
        "ui_text_sec": "#D8DEE9"
    },
    "solarized_dark": {
        "name": "Solarized Abyss",
        "color_bg": "#001E26",
        "color_passed": "#2AA198",
        "color_current": "#859900",
        "color_coming": "#073642",
        "color_text_primary": "#FDF6E3",
        "color_text_secondary": "#268BD2",
        "ui_canvas": "#002B36",
        "ui_bars": "#00212B",
        "ui_panel": "#073642",
        "ui_panel_alt": "#052E38",
        "ui_input": "#0E4351",
        "ui_hover": "#175263",
        "ui_border": "#1A596B",
        "ui_accent": "#2AA198",
        "ui_text_sec": "#93A1A1"
    },
    "cyberpunk": {
        "name": "Cyberpunk Neon",
        "color_bg": "#0A0712",
        "color_passed": "#FEE715",
        "color_current": "#F43F5E",
        "color_coming": "#221633",
        "color_text_primary": "#FAF5FF",
        "color_text_secondary": "#FEE715",
        "ui_canvas": "#140F21",
        "ui_bars": "#0F0B1A",
        "ui_panel": "#1E1630",
        "ui_panel_alt": "#191228",
        "ui_input": "#2A1F42",
        "ui_hover": "#392A5A",
        "ui_border": "#3A2A5B",
        "ui_accent": "#FEE715",
        "ui_text_sec": "#F43F5E"
    }
}

def _countdown_seed_date():
    """Next Jan 1 — seeded as the starter countdown target."""
    return f"{datetime.date.today().year + 1}-01-01"


DEFAULT_SETTINGS = {
    "font_face": "outfit",               # "outfit", "montserrat", "inter", "cinzel", "bahnschrift"
    "layout": "ref_10",                  # "ref_10", "balanced_20", "matrix_25", "calendar_53"
    "grid_zoom": 1.0,                    # 0.5 to 2.2 zoom multiplier
    "quote_mode": "preset",              # "preset", "custom", "daily_random"
    "preset_index": 0,
    "custom_quote": "You have power over your mind - not outside events. Realize this, and you will find strength.",
    "custom_author": "Marcus Aurelius",
    "show_progress_ring": True,
    "show_days_left": True,
    "show_quote": True,
    "highlight_current_day": True,
    # Countdown targets ("days until ...") rendered on the wallpaper
    "show_countdown": True,
    "countdown_index": 0,
    "countdown_targets": [
        {"label": "New Year", "date": _countdown_seed_date(), "yearly": True}
    ],
    # Colors
    "color_theme": "noir",
    "color_bg": "#070709",
    "color_passed": "#FFFFFF",
    "color_current": "#FFFFFF",
    "color_coming": "#2D2E38",
    "color_text_primary": "#FFFFFF",
    "color_text_secondary": "#9CA3AF",
    # Automation
    "auto_update_midnight": True,
    "start_with_windows": False,
    # Multi-monitor: render one correctly-sized image per display (Windows/macOS;
    # ignored on Linux where the desktop applies a single image everywhere)
    "multi_monitor": True,
    # Update checker: probe GitHub Releases once a day at launch and notify
    # through the tray when a newer version exists
    "check_updates": True,
    "last_update_check": "",
    "last_rendered_date": "",
    "daily_seed": 0
}

def load_quotes():
    """Load the user-editable quotes database, seeding it from the bundled copy if missing."""
    bundles = [
        os.path.join(paths.resource_dir(), "quotes.json"),
        os.path.join(paths.app_dir(), "quotes.json"),
    ]
    if not os.path.exists(QUOTES_FILE):
        for src in bundles:
            if not os.path.exists(src):
                continue
            try:
                shutil.copyfile(src, QUOTES_FILE)
                break  # only stop once a bundle actually made it to disk
            except Exception as e:
                print(f"Error seeding quotes.json from {src}: {e}")
    if os.path.exists(QUOTES_FILE):
        try:
            with open(QUOTES_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data and all(isinstance(q, dict) and q.get("text") for q in data):
                return data
            print("Warning: quotes.json has an unexpected shape, using fallback quote.")
        except Exception as e:
            print(f"Error loading quotes.json: {e}")
    return [
        {
            "text": "We have two lives, and the second begins when we realize we only have one.",
            "author": "Confucius",
            "category": "Perspective"
        }
    ]

def load_settings():
    settings = dict(DEFAULT_SETTINGS)
    _migrate_legacy_file("settings.json", SETTINGS_FILE)
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                settings.update(data)
        except Exception as e:
            print(f"Error loading settings.json, using defaults: {e}")
    return settings

def save_settings(settings):
    """Atomically persist settings (write to a temp file, then replace), so a
    crash or a full disk can never truncate/corrupt settings.json."""
    with _settings_lock:
        tmp_path = SETTINGS_FILE + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp_path, SETTINGS_FILE)
            return True
        except Exception as e:
            print(f"Error saving settings.json: {e}")
            try:
                if os.path.exists(tmp_path):
                    os.remove(tmp_path)
            except OSError:
                pass
            return False

def stamp_rendered_date():
    """Records that today's wallpaper has been generated/applied."""
    with _settings_lock:
        settings = load_settings()
        settings["last_rendered_date"] = datetime.date.today().strftime("%Y-%m-%d")
        return save_settings(settings)

def _migrate_legacy_file(filename, target_path):
    """Copies a previously-existing data file from the old app folder into data_dir."""
    if os.path.exists(target_path):
        return
    legacy = os.path.join(paths.app_dir(), filename)
    if os.path.exists(legacy):
        try:
            shutil.copyfile(legacy, target_path)
            print(f"[Config] Migrated {filename} to {target_path}")
        except Exception as e:
            print(f"[Config] Could not migrate {filename}: {e}")
