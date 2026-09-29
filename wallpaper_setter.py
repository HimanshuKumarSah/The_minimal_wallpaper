import json
import os
import shutil
import sys
import time

import paths
import wallpaper_setter_posix

# winreg/ctypes only exist on Windows; the module must stay importable on
# macOS/Linux so the platform dispatch below can route to the POSIX backend.
if sys.platform == "win32":
    import ctypes
    import winreg

IS_WINDOWS = sys.platform == "win32"

SPI_SETDESKWALLPAPER = 20
SPIF_UPDATEINIFILE = 0x01
SPIF_SENDCHANGE = 0x02

LOCK_CSP_KEY = r"Software\Microsoft\Windows\CurrentVersion\PersonalizationCSP"
LOCK_POLICY_KEY = r"Software\Policies\Microsoft\Windows\Personalization"
LOCK_RESULT_FILE = os.path.join(paths.data_dir(), "lockscreen_result.json")

def set_wallpaper(image_path):
    """
    Sets the desktop wallpaper to the specified image file path.
    Windows: registry + SystemParametersInfo. macOS/Linux: native desktop tools.
    """
    if not IS_WINDOWS:
        return wallpaper_setter_posix.set_wallpaper(image_path)
    return _set_wallpaper_windows(image_path)


def set_wallpapers(assignments, primary_path):
    """Applies per-display images: assignments is [(monitor_key, image_path)].

    ``primary_path`` is the app's main wallpaper file — it is used whenever the
    per-display API is unavailable (single assignment, COM failure) and by the
    POSIX/Linux backends. Returns (ok, message).
    """
    if not assignments:
        return False, "No wallpaper images to apply."
    if not IS_WINDOWS:
        return wallpaper_setter_posix.set_wallpapers(assignments, primary_path)
    keyed = [(key, path) for key, path in assignments if key]
    if len(keyed) <= 1:
        return set_wallpaper(primary_path)
    try:
        import win_wallpaper_com

        applied = win_wallpaper_com.set_wallpapers(
            [(key, os.path.abspath(path)) for key, path in keyed]
        )
        if applied:
            return True, f"Wallpaper updated on {applied} display(s)."
        # No exception, but nothing was applied — the fall-through below must
        # stay visible in the log or multi-monitor degradation looks silent.
        print("Note: per-monitor wallpaper API applied nothing; using single image.")
    except Exception as e:
        print(f"Note: per-monitor wallpaper API failed ({e}); using single image.")
    # COM unavailable or every SetWallpaper call failed → one image everywhere.
    return set_wallpaper(primary_path)


def _set_wallpaper_windows(image_path):
    """
    Sets the Windows desktop wallpaper to the specified image file path.
    Updates the registry and notifies Windows explorer.
    """
    abs_path = os.path.abspath(image_path)
    if not os.path.exists(abs_path):
        return False, f"Wallpaper file not found: {abs_path}"

    try:
        # 1. Update Windows Registry to persist the wallpaper
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Control Panel\Desktop",
            0,
            winreg.KEY_SET_VALUE
        )
        try:
            # WallpaperStyle: 10 = Fill, 6 = Fit, 0 = Center. 10 is standard for exact res images.
            winreg.SetValueEx(key, "WallpaperStyle", 0, winreg.REG_SZ, "10")
            winreg.SetValueEx(key, "TileWallpaper", 0, winreg.REG_SZ, "0")
            winreg.SetValueEx(key, "Wallpaper", 0, winreg.REG_SZ, abs_path)
        finally:
            winreg.CloseKey(key)

        # 2. Force "Picture" background mode so Slideshow/Spotlight can't
        #    override the static wallpaper at the next login/reboot.
        try:
            wallpapers_key = winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Wallpapers",
                0,
                winreg.KEY_SET_VALUE
            )
            try:
                winreg.SetValueEx(wallpapers_key, "BackgroundType", 0, winreg.REG_DWORD, 0)
            finally:
                winreg.CloseKey(wallpapers_key)
        except Exception as e:
            print(f"Warning: could not set BackgroundType: {e}")

        # 3. Multi-monitor systems: SystemParametersInfo alone can leave stale
        #    per-monitor images behind, so push the same file to every display
        #    through IDesktopWallpaper when more than one monitor is present.
        #    Single-monitor systems skip straight to the SPI path below.
        try:
            import win_wallpaper_com

            monitors = win_wallpaper_com.enumerate_monitors()
            if monitors and len(monitors) > 1:
                if win_wallpaper_com.set_all(abs_path):
                    return True, "Wallpaper updated successfully."
                # >1 display but set_all failed: log it, then SPI below applies
                # one image everywhere (per-display images may go stale).
                print("Note: per-monitor wallpaper API failed; using SPI fallback.")
        except Exception as e:
            print(f"Note: per-monitor wallpaper API unavailable ({e}); using SPI.")

        # 4. Inform Windows Shell to change the desktop wallpaper immediately
        result = ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETDESKWALLPAPER,
            0,
            abs_path,
            SPIF_UPDATEINIFILE | SPIF_SENDCHANGE
        )

        if result:
            return True, "Wallpaper updated successfully."
        else:
            return False, f"SystemParametersInfoW failed with code {ctypes.GetLastError()}"

    except Exception as e:
        return False, f"Exception while setting wallpaper: {e}"


# ==============================================================================
# LOCK SCREEN SUPPORT
# ------------------------------------------------------------------------------
# Windows offers no public per-user API for the lock screen image, so forcing a
# static lock screen requires writing HKLM registry keys (admin rights). We do
# this by briefly relaunching the app elevated (one UAC prompt) and waiting for
# the child process to report back via a small JSON result file.
# ==============================================================================

def write_lockscreen_result(ok, msg):
    """Records the outcome of an elevated lock-screen operation for the parent."""
    try:
        with open(LOCK_RESULT_FILE, "w", encoding="utf-8") as f:
            json.dump({"ok": bool(ok), "msg": str(msg)}, f)
    except Exception as e:
        # The parent reads this file to learn the outcome — a silent failure
        # here leaves it waiting on a result that never arrives.
        print(f"Could not write lock-screen result file: {e}")


def set_lockscreen_elevated(jpg_path):
    """Runs inside the elevated child: copies the image into the protected
    Windows lock-screen folder and stamps the HKLM registry keys."""
    if not IS_WINDOWS:
        return False, "Lock screen customization is only available on Windows."
    target_dir = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Web", "Screen")
    target = os.path.join(target_dir, "yearprogress_lock.jpg")
    try:
        if not os.path.exists(jpg_path):
            return False, f"Lock screen image not found: {jpg_path}"

        # Convert the supersampled PNG render to a properly-sized JPEG for the
        # lock screen (Windows expects a real JPEG; nothing larger than 4K needed).
        from PIL import Image as PILImage
        img = PILImage.open(jpg_path).convert("RGB")
        max_dim = 3840
        if max(img.size) > max_dim:
            ratio = max_dim / float(max(img.size))
            img = img.resize(
                (int(img.size[0] * ratio), int(img.size[1] * ratio)),
                PILImage.Resampling.LANCZOS,
            )
        tmp_jpg = os.path.join(paths.data_dir(), "lock_current.jpg")
        img.save(tmp_jpg, "JPEG", quality=92)

        if not os.path.exists(target_dir):
            os.makedirs(target_dir, exist_ok=True)
        shutil.copyfile(tmp_jpg, target)

        # PersonalizationCSP: how the lock screen picks up a custom picture.
        _set_hklm_value(LOCK_CSP_KEY, "LockScreenImagePath", winreg.REG_SZ, target)
        _set_hklm_value(LOCK_CSP_KEY, "LockScreenImageUrl", winreg.REG_SZ, target)
        _set_hklm_value(LOCK_CSP_KEY, "LockScreenImageStatus", winreg.REG_DWORD, 1)

        # Policy override for extra reliability across Windows versions.
        _set_hklm_value(LOCK_POLICY_KEY, "LockScreenImage", winreg.REG_SZ, target)
        return True, "Lock screen set to the current wallpaper. It will appear after you sign out and back in."
    except Exception as e:
        return False, f"Failed to set lock screen: {e}"


def clear_lockscreen_elevated():
    """Runs inside the elevated child: removes the forced lock screen image so
    Windows reverts to its default lock screen."""
    if not IS_WINDOWS:
        return False, "Lock screen customization is only available on Windows."
    target_dir = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "Web", "Screen")
    target = os.path.join(target_dir, "yearprogress_lock.jpg")
    try:
        for key_path, names in (
            (LOCK_CSP_KEY, ("LockScreenImagePath", "LockScreenImageUrl", "LockScreenImageStatus")),
            (LOCK_POLICY_KEY, ("LockScreenImage",)),
        ):
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE)
            except OSError:
                continue
            for name in names:
                try:
                    winreg.DeleteValue(key, name)
                except OSError:
                    pass
            winreg.CloseKey(key)
        try:
            if os.path.exists(target):
                os.remove(target)
        except OSError:
            pass
        return True, "Lock screen restored to the Windows default."
    except Exception as e:
        return False, f"Failed to restore default lock screen: {e}"


def _set_hklm_value(key_path, name, reg_type, value):
    try:
        key = winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, key_path, 0, winreg.KEY_SET_VALUE)
    except OSError as e:
        raise PermissionError(f"Can't create {key_path}: {e}")
    try:
        winreg.SetValueEx(key, name, 0, reg_type, value)
    finally:
        winreg.CloseKey(key)


def _run_admin_mode(mode, arg=None):
    """Relaunches the application elevated (UAC prompt) to run a lock-screen mode."""
    import sys
    exe = sys.executable
    # ShellExecuteW builds the child command line as: lpFile + " " + lpParameters,
    # so lpFile (the executable) already becomes argv[0]. It must NOT be repeated
    # inside lpParameters, otherwise the elevated child tries to open its own
    # executable as a script and dies before doing any work.
    if paths.is_frozen():
        command = f'{mode} "{arg}"' if arg else f"{mode}"
    else:
        script = os.path.join(paths.app_dir(), "main.py")
        command = f'"{script}" {mode} "{arg}"' if arg else f'"{script}" {mode}'
    shell32 = ctypes.windll.shell32
    # HINSTANCE is a pointer: without a 64-bit restype the truncated value can
    # look like a failure (<= 32) on some systems.
    shell32.ShellExecuteW.restype = ctypes.c_void_p
    result = shell32.ShellExecuteW(None, "runas", exe, command, None, 0)
    if not result or result <= 32:
        return False, f"Elevation failed (error code {result}). The action was cancelled."
    return True, None


def _run_admin_and_wait(mode, arg=None, timeout=20.0):
    """Launches the elevated child and returns its reported result."""
    try:
        if os.path.exists(LOCK_RESULT_FILE):
            os.remove(LOCK_RESULT_FILE)
    except OSError:
        pass
    launched, err = _run_admin_mode(mode, arg)
    if not launched:
        return False, err
    deadline = time.time() + timeout
    while time.time() < deadline:
        if os.path.exists(LOCK_RESULT_FILE):
            try:
                with open(LOCK_RESULT_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                return bool(data.get("ok", False)), data.get("msg", "Lock screen operation complete.")
            except Exception:
                time.sleep(0.2)
        time.sleep(0.2)
    return False, "Timed out waiting for the elevated operation to finish."


def apply_lockscreen(jpg_path):
    """GUI-facing entry point: set the lock screen to the given image."""
    if not IS_WINDOWS:
        return False, "Lock screen customization is only available on Windows."
    return _run_admin_and_wait("--lockscreen", jpg_path)


def restore_lockscreen():
    """GUI-facing entry point: clear the forced lock screen image."""
    if not IS_WINDOWS:
        return False, "Lock screen customization is only available on Windows."
    return _run_admin_and_wait("--lockscreen-clear")


if __name__ == "__main__":
    import wallpaper_generator
    png_path = wallpaper_generator.current_wallpaper_path()
    if not png_path:
        png_path = os.path.join(paths.data_dir(), "wallpaper_current.bmp")
    success, msg = set_wallpaper(png_path)
    print("Result:", success, msg)
