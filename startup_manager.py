import os
import sys

import paths
import startup_manager_posix

# winreg only exists on Windows; the module must stay importable on
# macOS/Linux so the dispatch below can reach the POSIX backend.
if sys.platform == "win32":
    import winreg

IS_WINDOWS = sys.platform == "win32"

APP_NAME = "YearProgressWallpaper"
REG_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

def get_startup_command():
    """Returns the optimal startup command line for the current environment."""
    if not IS_WINDOWS:
        return startup_manager_posix.get_startup_command()
    base_dir = paths.app_dir()
    exe_path = os.path.join(base_dir, "YearProgress.exe")
    
    if os.path.exists(exe_path):
        return f'"{exe_path}" --minimized'
    
    # Otherwise use pythonw for silent launch
    python_exe = sys.executable
    if python_exe.lower().endswith("python.exe"):
        # Keep the original casing: only the interpreter filename changes.
        pythonw = python_exe[: -len("python.exe")] + "pythonw.exe"
        if os.path.exists(pythonw):
            python_exe = pythonw

    main_py = os.path.join(base_dir, "main.py")
    return f'"{python_exe}" "{main_py}" --minimized'

def is_startup_enabled():
    """Checks whether the application is registered for login startup."""
    if not IS_WINDOWS:
        return startup_manager_posix.is_startup_enabled()
    key = None
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_RUN_KEY,
            0,
            winreg.KEY_READ
        )
        val, _ = winreg.QueryValueEx(key, APP_NAME)
        return bool(val)
    except FileNotFoundError:
        return False
    except Exception as e:
        print(f"Error checking startup registry: {e}")
        return False
    finally:
        if key is not None:
            try:
                winreg.CloseKey(key)
            except OSError:
                pass

def set_startup(enable=True):
    """Enables or disables auto-startup (Windows Run key / LaunchAgent / XDG)."""
    if not IS_WINDOWS:
        return startup_manager_posix.set_startup(enable)
    key = None
    try:
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_RUN_KEY,
            0,
            winreg.KEY_SET_VALUE
        )
        if enable:
            cmd = get_startup_command()
            winreg.SetValueEx(key, APP_NAME, 0, winreg.REG_SZ, cmd)
            return True, f"Startup enabled: {cmd}"
        try:
            winreg.DeleteValue(key, APP_NAME)
        except FileNotFoundError:
            pass
        return True, "Startup disabled."
    except Exception as e:
        return False, f"Failed to modify startup registry: {e}"
    finally:
        if key is not None:
            try:
                winreg.CloseKey(key)
            except OSError:
                pass

if __name__ == "__main__":
    print("Is startup enabled?", is_startup_enabled())
    print("Startup command:", get_startup_command())
