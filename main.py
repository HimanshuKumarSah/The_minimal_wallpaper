import argparse
import datetime
import os
import random
import sys

import config
import wallpaper_generator
import wallpaper_setter
from app_tray import AppTray
from scheduler import DailyScheduler

try:
    from gui_webview import YearProgressWebviewApp
    HAS_WEBVIEW = True
except Exception as e:
    print(f"pywebview not available ({e}), falling back to Tkinter UI")
    HAS_WEBVIEW = False

try:
    import customtkinter as ctk

    from ui import YearProgressUI
    HAS_TK_UI = True
except Exception as e:
    # Tk may be missing on minimal Linux installs; the webview UI doesn't need it.
    print(f"Tkinter UI unavailable ({e})")
    ctk = None
    YearProgressUI = None
    HAS_TK_UI = False


class YearProgressApp:
    def __init__(self, start_minimized=False):
        self.settings = config.load_settings()
        self.quotes_list = config.load_quotes()
        self.start_minimized = start_minimized
        
        # Setup modern CustomTkinter root window
        self.root = ctk.CTk()
        if self.start_minimized:
            self.root.withdraw()
        self.ui = YearProgressUI(
            self.root, 
            on_wallpaper_updated=self.on_wallpaper_applied,
            on_exit_app=self.quit_app,
            start_minimized=self.start_minimized
        )
            
        # Setup System Tray
        self.tray = AppTray(
            on_show_window=self.show_window_from_tray,
            on_update_now=self.update_wallpaper_now,
            on_next_quote=self.next_quote_from_tray,
            on_exit=self.quit_app
        )
        self.tray.start()
        
        # Setup Scheduler for midnight daily updates
        self.scheduler = DailyScheduler(self.on_midnight_trigger)
        self.scheduler.start()
        
        # Auto-apply wallpaper on initial launch to ensure it's up to date
        # (deferred so the UI appears immediately; runs after mainloop starts)
        if wallpaper_generator.requires_daily_update(self.settings):
            self.root.after(300, lambda: self.update_wallpaper_now(notify=False))

    def show_window_from_tray(self):
        self.root.after(0, self.ui.show_window)

    def update_wallpaper_now(self, notify=True):
        self.settings = config.load_settings()
        try:
            wall_path, _ = wallpaper_generator.generate_wallpaper(self.settings)
            set_path = os.path.splitext(wall_path)[0] + ".png"
            success, msg = wallpaper_setter.set_wallpaper(set_path)
            if success:
                print(f"[{datetime.datetime.now()}] Wallpaper updated successfully.")
                config.stamp_rendered_date()
                if notify and self.tray:
                    today_str = datetime.date.today().strftime("%B %d, %Y")
                    self.tray.notify("Year Progress", f"Wallpaper updated for {today_str}!")
                # Update UI preview if open
                self.root.after(0, self.ui.schedule_preview_update, True)
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
            # Tk widgets must only be touched from the main thread; the tray
            # callback runs on a background thread, so marshal via root.after.
            # Keep the UI's own settings dict in sync too, otherwise its next
            # save would write the old preset_index back over ours.
            self.ui.settings["preset_index"] = next_idx
            if hasattr(self.ui, "opt_quotes") and next_idx < len(self.ui.quote_titles):
                self.root.after(0, lambda i=next_idx: self.ui.opt_quotes.set(self.ui.quote_titles[i]))
        else:
            self.settings["daily_seed"] = random.randint(0, 10000)
            
        config.save_settings(self.settings)
        self.update_wallpaper_now(notify=True)

    def on_wallpaper_applied(self, path):
        pass

    def quit_app(self):
        print("[App] Quitting application...")
        if self.scheduler:
            self.scheduler.stop()
        if self.tray:
            self.tray.stop()
        self.root.after(100, self.root.destroy)

    def run(self):
        try:
            self.root.mainloop()
        except KeyboardInterrupt:
            self.quit_app()

def main():
    parser = argparse.ArgumentParser(description="Year Progress Wallpaper for Windows, macOS and Linux")
    parser.add_argument("--minimized", action="store_true", help="Start directly minimized in system tray")
    parser.add_argument("--startup", action="store_true", help="Launched from OS login startup")
    parser.add_argument("--update-now", action="store_true", help="Generate and set wallpaper immediately and exit")
    parser.add_argument("--lockscreen", metavar="IMAGE", help="Set the given image as the Windows lock screen (run elevated; internal use)")
    parser.add_argument("--lockscreen-clear", action="store_true", help="Restore the default Windows lock screen (run elevated; internal use)")
    args = parser.parse_args()
    
    # Elevated lock-screen modes (invoked internally with a UAC prompt).
    if args.lockscreen is not None:
        ok, msg = wallpaper_setter.set_lockscreen_elevated(args.lockscreen)
        wallpaper_setter.write_lockscreen_result(ok, msg)
        sys.exit(0 if ok else 1)
    if args.lockscreen_clear:
        ok, msg = wallpaper_setter.clear_lockscreen_elevated()
        wallpaper_setter.write_lockscreen_result(ok, msg)
        sys.exit(0 if ok else 1)
    
    if args.update_now:
        settings = config.load_settings()
        wall_path, _ = wallpaper_generator.generate_wallpaper(settings)
        set_path = os.path.splitext(wall_path)[0] + ".png"
        success, msg = wallpaper_setter.set_wallpaper(set_path)
        print(f"Update now result: {success} ({msg})")
        sys.exit(0 if success else 1)
        
    start_minimized = args.minimized or args.startup
    if HAS_WEBVIEW:
        app = YearProgressWebviewApp(start_minimized=start_minimized)
    elif HAS_TK_UI:
        app = YearProgressApp(start_minimized=start_minimized)
    else:
        print("No UI backend available: install pywebview or tkinter.")
        sys.exit(1)
    app.run()

if __name__ == "__main__":
    main()
