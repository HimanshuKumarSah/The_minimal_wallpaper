"""Shared application logic for the Tk and pywebview front ends.

Each front end keeps its own window, tray, and quit plumbing, but both run
the same wallpaper / scheduler / quote workflows.  BaseApp holds those so the
two copies can't drift apart again (they already had: the midnight seed range
and the stamp-vs-print order differed between the classes).
"""

import datetime
import random
import threading

import config
import update_checker
import wallpaper_apply
from scheduler import DailyScheduler


class BaseApp:
    """Front-end-agnostic app logic.

    Subclasses set up their own window and tray, call :meth:`_start_services`
    once the tray exists, and implement the two hooks below.
    """

    # Defaults so quit paths stay safe even if a subclass exits before
    # _start_services() has run.
    tray = None
    scheduler = None

    def _on_render_done(self):
        """Front-end hook: push the freshly rendered preview into the panel."""

    def _sync_preset_selection(self, next_idx):
        """Front-end hook: reflect a tray-driven preset change in an open UI."""

    def _start_services(self):
        """Start the midnight scheduler and the daily release check.

        Call after the tray exists — the release check notifies through it.
        """
        self.scheduler = DailyScheduler(self.on_midnight_trigger)
        self.scheduler.start()
        threading.Thread(
            target=update_checker.check_and_notify,
            args=(self.tray,),
            daemon=True,
        ).start()

    def update_wallpaper_now(self, notify=True):
        self.settings = config.load_settings()
        try:
            success, msg, _png = wallpaper_apply.apply_wallpaper(self.settings)
            if success:
                config.stamp_rendered_date()
                print(f"[{datetime.datetime.now()}] Wallpaper updated successfully.")
                if notify and self.tray:
                    today_str = datetime.date.today().strftime("%B %d, %Y")
                    self.tray.notify(
                        "Year Progress", f"Wallpaper updated for {today_str}!"
                    )
                self._on_render_done()
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
        # If daily random quote is enabled, pick a fresh seed
        if self.settings.get("quote_mode") == "daily_random":
            self.settings["daily_seed"] = random.randint(0, 10000)
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
            self._sync_preset_selection(next_idx)
        else:
            self.settings["daily_seed"] = random.randint(0, 10000)
        config.save_settings(self.settings)
        self.update_wallpaper_now(notify=True)
