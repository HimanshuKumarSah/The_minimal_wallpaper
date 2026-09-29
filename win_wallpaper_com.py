"""Per-monitor wallpaper control through the Windows IDesktopWallpaper COM API.

SystemParametersInfo applies one image to the whole desktop, so every monitor
receives the primary display's render (stretched/cropped on different sizes).
IDesktopWallpaper (Windows 8+) accepts a distinct image per monitor, which is
what the Settings app itself uses.

This module is intentionally self-contained: on non-Windows platforms every
function reports "unavailable" so callers can dispatch without platform checks.
All functions swallow COM errors and return None/0 instead of raising, because
the wallpaper pipeline treats the COM path as an optional enhancement with a
SystemParametersInfo fallback.
"""

import ctypes
import ctypes.wintypes
import sys
import uuid

IS_WINDOWS = sys.platform == "win32"

# CLSID_DesktopWallpaper / IID_IDesktopWallpaper from shobjidl_core.h.
_CLSID_DESKTOP_WALLPAPER = "C2CF3110-460E-4fc1-B9D0-8A1C0C9CC4BD"
_IID_IDESKTOP_WALLPAPER = "B92B56A9-8B55-4E14-9A89-0199BBB6F93B"

# IDesktopWallpaper method slots in the COM vtable (IUnknown occupies 0-2),
# verified against the Windows SDK ShObjIdl_core.h declaration order.
_VT_SET_WALLPAPER = 3
_VT_GET_MONITOR_PATH_AT = 5
_VT_GET_MONITOR_COUNT = 6
_VT_GET_MONITOR_RECT = 7

_CLSCTX_ALL = 0x17  # in-proc server + handler + local/remote server
_COINIT_APARTMENTTHREADED = 0x2
_S_OK = 0
_S_FALSE = 1  # CoInitializeEx: already initialized in this mode (counts as success)
_RPC_E_CHANGED_MODE = 0x80010106  # thread already initialized in another mode

if IS_WINDOWS:
    _ole32 = ctypes.windll.ole32

    class _GUID(ctypes.Structure):
        _fields_ = [
            ("Data1", ctypes.c_uint32),
            ("Data2", ctypes.c_uint16),
            ("Data3", ctypes.c_uint16),
            ("Data4", ctypes.c_ubyte * 8),
        ]

    class _RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.wintypes.LONG),
            ("top", ctypes.wintypes.LONG),
            ("right", ctypes.wintypes.LONG),
            ("bottom", ctypes.wintypes.LONG),
        ]

    def _guid(text):
        u = uuid.UUID(text)
        return _GUID(u.time_low, u.time_mid, u.time_hi_version, (ctypes.c_ubyte * 8)(*u.bytes[8:]))

    def _vtable_fn(ptr, index, restype, *argtypes):
        """Resolves a stdcall COM method from an interface pointer."""
        vtbl = ctypes.c_void_p.from_address(ptr).value
        addr = ctypes.c_void_p.from_address(vtbl + index * 8).value
        proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
        return proto(addr)

    def _com_init():
        """Initializes COM for the calling thread.

        Returns (usable, owns_init): ``usable`` means CoCreate may proceed;
        ``owns_init`` tells the caller it must CoUninitialize to stay balanced
        (never true for RPC_E_CHANGED_MODE, where the apartment belongs to
        someone else).
        """
        hr = _ole32.CoInitializeEx(None, _COINIT_APARTMENTTHREADED)
        if hr in (_S_OK, _S_FALSE):
            return True, True
        if hr == _RPC_E_CHANGED_MODE:
            return True, False
        return False, False

    def _create_interface():
        """CoCreates IDesktopWallpaper.

        Returns (interface_pointer, owns_init); the caller must call
        CoUninitialize in its own finally only when ``owns_init`` is True.
        """
        usable, owns_init = _com_init()
        if not usable:
            return None, False
        clsid = _guid(_CLSID_DESKTOP_WALLPAPER)
        iid = _guid(_IID_IDESKTOP_WALLPAPER)
        ptr = ctypes.c_void_p()
        hr = _ole32.CoCreateInstance(
            ctypes.byref(clsid), None, _CLSCTX_ALL, ctypes.byref(iid), ctypes.byref(ptr)
        )
        if hr != _S_OK or not ptr.value:
            # We incremented the apartment count but have no interface to hand
            # off — release it here so repeated failures can't pin the thread.
            if owns_init:
                _ole32.CoUninitialize()
            return None, False
        return ptr.value, owns_init


def enumerate_monitors():
    """Returns [(key, width, height, is_primary)] or None when COM is unavailable.

    ``key`` is the IDesktopWallpaper monitor device path — the token accepted by
    :func:`set_wallpapers`. Detached monitors (present in the count but with no
    rect) are skipped, matching the API's documented behaviour.
    """
    if not IS_WINDOWS:
        return None
    ptr, owns_init = _create_interface()
    if not ptr:
        return None
    try:
        count_fn = _vtable_fn(ptr, _VT_GET_MONITOR_COUNT, ctypes.c_long, ctypes.POINTER(ctypes.c_uint))
        count = ctypes.c_uint(0)
        if count_fn(ptr, ctypes.byref(count)) != _S_OK:
            return None

        path_fn = _vtable_fn(
            ptr, _VT_GET_MONITOR_PATH_AT, ctypes.c_long, ctypes.c_uint, ctypes.POINTER(ctypes.c_wchar_p)
        )
        rect_fn = _vtable_fn(
            ptr, _VT_GET_MONITOR_RECT, ctypes.c_long, ctypes.c_wchar_p, ctypes.POINTER(_RECT)
        )

        monitors = []
        for i in range(count.value):
            path_buf = ctypes.c_wchar_p()
            if path_fn(ptr, i, ctypes.byref(path_buf)) != _S_OK or not path_buf.value:
                continue
            key = path_buf.value
            try:
                rect = _RECT()
                if rect_fn(ptr, key, ctypes.byref(rect)) != _S_OK:
                    continue  # detached monitor
                w = rect.right - rect.left
                h = rect.bottom - rect.top
                if w <= 0 or h <= 0:
                    continue
                # Virtual-screen coordinates put the primary monitor at (0, 0).
                is_primary = rect.left == 0 and rect.top == 0
                monitors.append((key, w, h, is_primary))
            finally:
                _ole32.CoTaskMemFree(ctypes.cast(path_buf, ctypes.c_void_p))
        return monitors or None
    except Exception as e:
        # Swallowing here would make wallpaper_setter's fallback look silent —
        # log why the per-monitor path bailed before returning None.
        print(f"[COM] Monitor enumeration failed: {e}")
        return None
    finally:
        if owns_init:
            _ole32.CoUninitialize()


def set_wallpapers(assignments):
    """Sets a distinct wallpaper per monitor: [(monitor_key, abs_path)].

    Returns the number of monitors updated, or None when COM is unavailable
    (callers fall back to SystemParametersInfo). A failure on individual
    monitors is tolerated as long as at least one image was applied.
    """
    if not IS_WINDOWS or not assignments:
        return None
    ptr, owns_init = _create_interface()
    if not ptr:
        return None
    try:
        set_fn = _vtable_fn(ptr, _VT_SET_WALLPAPER, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_wchar_p)
        applied = 0
        for key, path in assignments:
            if not key:
                continue
            if set_fn(ptr, key, path) == _S_OK:
                applied += 1
        return applied
    except Exception as e:
        print(f"[COM] Per-monitor SetWallpaper failed: {e}")
        return None
    finally:
        if owns_init:
            _ole32.CoUninitialize()


def set_all(path):
    """Applies one image to every monitor (monitorID = NULL). True on success."""
    if not IS_WINDOWS:
        return False
    ptr, owns_init = _create_interface()
    if not ptr:
        return False
    try:
        set_fn = _vtable_fn(ptr, _VT_SET_WALLPAPER, ctypes.c_long, ctypes.c_wchar_p, ctypes.c_wchar_p)
        return set_fn(ptr, None, path) == _S_OK
    except Exception as e:
        print(f"[COM] set_all (every monitor) failed: {e}")
        return False
    finally:
        if owns_init:
            _ole32.CoUninitialize()
