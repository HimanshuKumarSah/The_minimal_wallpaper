import base64
import datetime
import os
import random
import threading
import time

import webview

import config
import paths
import platform_info
import startup_manager
import wallpaper_generator
import wallpaper_setter
from app_tray import AppTray
from scheduler import DailyScheduler

WEB_DIR = os.path.join(paths.resource_dir(), "web")
INDEX_HTML = os.path.join(WEB_DIR, "index.html")


class WebviewBridge:
    def __init__(self, app):
        self.app = app

    def get_initial_data(self):
        settings = config.load_settings()
        quotes = config.load_quotes()
        
        today = datetime.date.today()
        year = today.year
        day_of_year = today.timetuple().tm_yday
        is_leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
        total_days = 366 if is_leap else 365
        days_left = max(0, total_days - day_of_year)
        pct = (day_of_year / total_days) * 100.0
        
        w, h = wallpaper_generator.get_screen_resolution()

        # Return the cached preview thumbnail so the control panel hydrates
        # instantly; a fresh render is kicked off asynchronously from the
        # front-end (refreshPreview) so a slow render can never block or blank
        # the UI.
        prev_data_url = self.get_preview_data_url()

        return {
            "settings": settings,
            "quotes": quotes,
            "themes": config.COLOR_THEMES,
            "fonts": config.FONT_PRESETS,
            "stats": {
                "day_of_year": day_of_year,
                "total_days": total_days,
                "days_left": days_left,
                "pct": round(pct, 1),
                "year": year
            },
            "display": {
                "width": w,
                "height": h
            },
            "is_startup": startup_manager.is_startup_enabled(),
            "platform": platform_info.as_dict(),
            "preview_url": prev_data_url
        }

    def get_preview_data_url(self, path=None):
        if path is None:
            path = os.path.join(paths.data_dir(), "preview_thumbnail.png")
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    encoded = base64.b64encode(f.read()).decode("utf-8")
                    return f"data:image/png;base64,{encoded}"
            except Exception as e:
                print(f"Error reading preview thumbnail: {e}")
        return None

    def update_preview(self, settings):
        try:
            w, h = wallpaper_generator.get_screen_resolution()
            _, prev_path = wallpaper_generator.generate_wallpaper(settings, width=w, height=h, preview_only=True)
            return self.get_preview_data_url(prev_path)
        except Exception as e:
            print(f"Error updating preview: {e}")
            return ""

    def save_settings(self, settings):
        try:
            # Volatile keys owned by the render/scheduler paths — the web UI
            # only echoes them back, so never let a stale copy overwrite disk.
            disk = config.load_settings()
            for key in ("last_rendered_date", "daily_seed"):
                if key in disk:
                    settings[key] = disk[key]
            ok = config.save_settings(settings)
            self.app.settings = settings
            return ok
        except Exception as e:
            print(f"Error saving settings: {e}")
            return False

    def apply_wallpaper(self, settings):
        self.save_settings(settings)
        try:
            wall_path, _ = wallpaper_generator.generate_wallpaper(settings, preview_only=False)
            set_path = os.path.splitext(wall_path)[0] + ".png"
            success, msg = wallpaper_setter.set_wallpaper(set_path)
            now_str = datetime.datetime.now().strftime("%I:%M:%S %p")
            if success:
                config.stamp_rendered_date()
                return {"success": True, "msg": f"✓ Wallpaper applied at {now_str}"}
            else:
                return {"success": False, "msg": f"⚠ {msg}"}
        except Exception as e:
            return {"success": False, "msg": f"⚠ Error: {e}"}

    def set_startup(self, enabled):
        success, msg = startup_manager.set_startup(enabled)
        return {"success": success, "msg": msg}

    def is_startup_enabled(self):
        return startup_manager.is_startup_enabled()

    def set_lockscreen(self):
        img = wallpaper_generator.current_wallpaper_path()
        if not img:
            return {"success": False, "msg": "No wallpaper applied yet. Click Apply Wallpaper first."}
        success, msg = wallpaper_setter.apply_lockscreen(img)
        return {"success": success, "msg": msg}

    def clear_lockscreen(self):
        success, msg = wallpaper_setter.restore_lockscreen()
        return {"success": success, "msg": msg}

    def minimize_to_tray(self):
        self.app.minimize_to_tray()

    def get_time_until_midnight(self):
        h, m, s = DailyScheduler.get_time_until_midnight()
        return {"h": h, "m": m, "s": s}


class YearProgressWebviewApp:
    def __init__(self, start_minimized=False):
        self.settings = config.load_settings()
        self.quotes_list = config.load_quotes()
        self.start_minimized = start_minimized
        self.window = None
        self.bridge = WebviewBridge(self)

        # Background Scheduler for Midnight updates
        self.scheduler = DailyScheduler(self.on_midnight_trigger)
        self.scheduler.start()

        # Auto-apply wallpaper on launch if today's render is missing/stale
        if wallpaper_generator.requires_daily_update(self.settings):
            self.update_wallpaper_now(notify=False)

        # System Tray Integration
        self.tray = AppTray(
            on_show_window=self.show_window_from_tray,
            on_update_now=self.update_wallpaper_now,
            on_next_quote=self.next_quote_from_tray,
            on_exit=self.quit_app
        )
        self.tray.start()

        # Build Webview Window
        self._build_window()

    def _build_window(self):
        # Create pywebview window with Microsoft Edge WebView2
        self.window = webview.create_window(
            title="Year Progress • Studio Control Center",
            url=INDEX_HTML,
            js_api=self.bridge,
            width=1240,
            height=820,
            min_size=(1060, 700),
            background_color="#0A0B0F",
            text_select=False,
            hidden=self.start_minimized
        )

        # Hook window events
        self.window.events.closing += self._on_window_closing

    def _on_window_closing(self):
        """Intercept close button to minimize cleanly into system tray."""
        self.minimize_to_tray()
        return False  # Cancels the close and keeps app alive in background tray

    def show_window_from_tray(self):
        if self.window:
            self.window.show()
            self.window.restore()

    def minimize_to_tray(self):
        if self.window:
            self.window.hide()

    def _refresh_ui(self):
        """Pushes the latest settings/preview into an open control panel window."""
        if self.window:
            try:
                self.window.evaluate_js("window.refreshFromTray && window.refreshFromTray()")
            except Exception as e:
                print(f"Could not refresh webview UI: {e}")

    def update_wallpaper_now(self, notify=True):
        self.settings = config.load_settings()
        try:
            wall_path, _ = wallpaper_generator.generate_wallpaper(self.settings, preview_only=False)
            set_path = os.path.splitext(wall_path)[0] + ".png"
            success, msg = wallpaper_setter.set_wallpaper(set_path)
            if success:
                config.stamp_rendered_date()
                print(f"[{datetime.datetime.now()}] Wallpaper updated successfully.")
                self._refresh_ui()
                if notify and self.tray:
                    today_str = datetime.date.today().strftime("%B %d, %Y")
                    self.tray.notify("Year Progress", f"Wallpaper updated for {today_str}!")
            else:
                print(f"[{datetime.datetime.now()}] Failed to set wallpaper: {msg}")
        except Exception as e:
            print(f"Error during wallpaper update: {e}")

    def on_midnight_trigger(self, reason="midnight_daily_update"):
        print(f"[App] Midnight update triggered: {reason}")
        self.settings = config.load_settings()
        if not self.settings.get("auto_update_midnight", True):
            print("[App] Midnight update skipped (auto_update_midnight is disabled).")
            return
        if self.settings.get("quote_mode") == "daily_random":
            self.settings["daily_seed"] = random.randint(0, 1000)
            config.save_settings(self.settings)
        self.update_wallpaper_now(notify=True)

    def next_quote_from_tray(self):
        self.settings = config.load_settings()
        mode = self.settings.get("quote_mode", "preset")
        if mode == "preset":
            if self.quotes_list:
                curr_idx = self.settings.get("preset_index", 0)
                next_idx = (curr_idx + 1) % len(self.quotes_list)
            else:
                next_idx = 0
            self.settings["preset_index"] = next_idx
        else:
            self.settings["daily_seed"] = random.randint(0, 10000)
        config.save_settings(self.settings)
        self.update_wallpaper_now(notify=True)
        self._refresh_ui()

    def quit_app(self):
        print("[App] Quitting application...")
        if self.scheduler:
            self.scheduler.stop()
        if self.tray:
            self.tray.stop()
            self.tray = None
        if self.window:
            self.window.destroy()
            self.window = None
        # Safety net: if the webview loop doesn't wind down on its own
        # (e.g. destroy() ran on a background thread), force a clean process
        # exit instead of leaving a zombie.
        def _hard_exit():
            time.sleep(3)
            os._exit(0)
        threading.Thread(target=_hard_exit, daemon=True).start()

    def run(self):
        webview.start(debug=False)


if __name__ == "__main__":
    app = YearProgressWebviewApp()
    app.run()
