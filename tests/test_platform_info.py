import importlib
import sys

import platform_info


def test_platform_info_structure():
    info = platform_info.as_dict()
    assert set(info) == {"os", "lockscreen", "startup_title", "startup_note"}
    assert info["os"] in {"windows", "macos", "linux"}
    # The lock screen feature must follow the OS flag exactly.
    assert info["lockscreen"] is (info["os"] == "windows")


def test_platform_info_labels_per_os(monkeypatch):
    real_platform = sys.platform

    with monkeypatch.context() as m:
        m.setattr(sys, "platform", "linux")
        importlib.reload(platform_info)
        assert platform_info.OS_NAME == "linux"
        assert platform_info.SUPPORTS_LOCKSCREEN is False
        assert "~/.config/autostart" in platform_info.STARTUP_NOTE
        assert "Windows" not in platform_info.STARTUP_TITLE

    with monkeypatch.context() as m:
        m.setattr(sys, "platform", "darwin")
        importlib.reload(platform_info)
        assert platform_info.OS_NAME == "macos"
        assert platform_info.SUPPORTS_LOCKSCREEN is False
        assert "LaunchAgents" in platform_info.STARTUP_NOTE

    with monkeypatch.context() as m:
        m.setattr(sys, "platform", "win32")
        importlib.reload(platform_info)
        assert platform_info.OS_NAME == "windows"
        assert platform_info.SUPPORTS_LOCKSCREEN is True
        assert "Registry" in platform_info.STARTUP_NOTE

    # Restore module constants for whatever host this suite runs on.
    with monkeypatch.context() as m:
        m.setattr(sys, "platform", real_platform)
        importlib.reload(platform_info)
