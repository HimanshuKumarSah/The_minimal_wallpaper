import argparse
import sys

import config
import wallpaper_apply
import wallpaper_generator
import wallpaper_setter
from app_base import BaseApp
from app_tray import AppTray

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


class YearProgressApp(BaseApp):
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

        # Midnight scheduler + daily GitHub release check (daemon thread;
        # no-op when disabled or already checked today)
        self._start_services()
        
        # Auto-apply wallpaper on initial launch to ensure it's up to date
        # (deferred so the UI appears immediately; runs after mainloop starts)
        if wallpaper_generator.requires_daily_update(self.settings):
            self.root.after(300, lambda: self.update_wallpaper_now(notify=False))

    def _on_render_done(self):
        # Tk widgets must only be touched from the main thread; the tray and
        # scheduler callbacks run on background threads, so marshal via after.
        self.root.after(0, self.ui.schedule_preview_update, True)

    def _sync_preset_selection(self, next_idx):
        # Keep the UI's own settings dict in sync, otherwise its next save
        # would write the old preset_index back over ours, and move the
        # quotes dropdown to match (marshalled to the Tk main thread).
        self.ui.settings["preset_index"] = next_idx
        if hasattr(self.ui, "opt_quotes") and next_idx < len(self.ui.quote_titles):
            self.root.after(
                0, lambda i=next_idx: self.ui.opt_quotes.set(self.ui.quote_titles[i])
            )

    def show_window_from_tray(self):
        self.root.after(0, self.ui.show_window)

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
        success, msg, _png = wallpaper_apply.apply_wallpaper(settings)
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
