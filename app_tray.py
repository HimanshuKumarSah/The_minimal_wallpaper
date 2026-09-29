import os

try:
    import pystray
    HAS_TRAY = True
except Exception as e:
    # Linux ships several tray backends (AppIndicator/GTK/X11) and not every
    # system has one installed. The app must keep running windowed without a
    # tray instead of dying at import time.
    pystray = None
    HAS_TRAY = False
    print(f"System tray unavailable ({e}); running without it.")

from PIL import Image

import paths
import platform_info
import startup_manager


class AppTray:
    def __init__(self, on_show_window, on_update_now, on_next_quote, on_exit):
        self.on_show_window = on_show_window
        self.on_update_now = on_update_now
        self.on_next_quote = on_next_quote
        self.on_exit = on_exit
        self.icon = None

    def _get_icon_image(self):
        icon_path = os.path.join(paths.resource_dir(), "app_icon.png")
        if os.path.exists(icon_path):
            return Image.open(icon_path)
        # Fallback tiny icon
        img = Image.new("RGBA", (64, 64), (10, 10, 15, 255))
        return img

    def _toggle_startup(self, icon, item):
        currently_enabled = startup_manager.is_startup_enabled()
        ok, msg = startup_manager.set_startup(not currently_enabled)
        if not ok:
            # Without this the registry failure is completely silent.
            self.notify("Year Progress", msg)
        if self.icon:
            self.icon.update_menu()

    def _is_startup_checked(self, item):
        return startup_manager.is_startup_enabled()

    def _build_menu(self):
        return pystray.Menu(
            pystray.MenuItem("Open Year Progress", lambda icon, item: self.on_show_window(), default=True),
            pystray.MenuItem("Update Wallpaper Now", lambda icon, item: self.on_update_now()),
            pystray.MenuItem("Next Motivational Quote", lambda icon, item: self.on_next_quote()),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                platform_info.STARTUP_LABEL,
                self._toggle_startup,
                checked=self._is_startup_checked
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit", lambda icon, item: self.on_exit())
        )

    def start(self):
        if not HAS_TRAY or self.icon is not None:
            return
        image = self._get_icon_image()
        self.icon = pystray.Icon(
            "YearProgressWallpaper",
            image,
            "Year Progress Wallpaper",
            menu=self._build_menu()
        )
        self.icon.run_detached()

    def notify(self, title, message):
        if HAS_TRAY and self.icon:
            try:
                self.icon.notify(message, title)
            except Exception as e:
                print(f"Error showing tray notification: {e}")

    def stop(self):
        if self.icon:
            self.icon.stop()
            self.icon = None
