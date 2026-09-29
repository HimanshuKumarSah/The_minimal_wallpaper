# -*- mode: python ; coding: utf-8 -*-
# Cross-platform PyInstaller spec: builds on Windows, macOS and Linux.
#   Windows : dist/YearProgress.exe   (onefile windowed app)
#   macOS   : dist/YearProgress.app   (bundle created below)
#   Linux   : dist/YearProgress       (onefile ELF binary)
import re
import sys

from PyInstaller.utils.hooks import collect_all

# Single source of truth for the release version: parse APP_VERSION straight
# out of config.py (text-level) so the spec never imports app modules — their
# import side effects (directory creation etc.) don't belong in a build step.
with open(f"{SPECPATH}/config.py", encoding="utf-8") as _cfg_file:
    APP_VERSION = re.search(
        r'APP_VERSION\s*=\s*"([^"]+)"', _cfg_file.read()
    ).group(1)

datas = [('web', 'web'), ('assets', 'assets'), ('quotes.json', '.'), ('app_icon.png', '.'), ('app_icon.ico', '.')]
binaries = []
# Nothing outside the app's own imports needs forcing; win32timezone (pywin32)
# was removed because neither the app nor pystray/webview import it.
hiddenimports = []
tmp_ret = collect_all('webview')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('pystray')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='YearProgress',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # .ico is Windows-only; other platforms take the default executable icon
    # (a macOS .icns can be added here when a signed build is set up).
    icon=['app_icon.ico'] if sys.platform == 'win32' else None,
)

if sys.platform == 'darwin':
    app = BUNDLE(
        exe,
        name='YearProgress.app',
        icon=None,
        bundle_identifier='com.yearprogress.wallpaper',
        version=APP_VERSION,
        info_plist={
            'NSHighResolutionCapable': True,
            'CFBundleShortVersionString': APP_VERSION,
            'NSHumanReadableCopyright': 'Year Progress Wallpaper',
        },
    )
