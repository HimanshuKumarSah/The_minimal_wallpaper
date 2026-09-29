@echo off
title Year Progress Wallpaper
cd /d "%~dp0"

rem Order: packaged exe -> known local interpreter -> python.exe on PATH ->
rem Python launcher -> pythonw.exe on PATH -> clear error. Microsoft Store
rem app-execution aliases are skipped: running them just opens the Store.
if exist "%~dp0YearProgress.exe" (
    start "" "%~dp0YearProgress.exe"
    exit /b
)
if exist "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" (
    start "" "%LOCALAPPDATA%\Python\pythoncore-3.14-64\python.exe" "%~dp0main.py"
    exit /b
)

for /f "delims=" %%P in ('where python.exe 2^>nul') do (
    echo %%P| findstr /I "WindowsApps" >nul
    if errorlevel 1 (
        start "" "%%P" "%~dp0main.py"
        exit /b
    )
)
for /f "delims=" %%P in ('where py.exe 2^>nul') do (
    echo %%P| findstr /I "WindowsApps" >nul
    if errorlevel 1 (
        start "" "%%P" -3 "%~dp0main.py"
        exit /b
    )
)
for /f "delims=" %%P in ('where pythonw.exe 2^>nul') do (
    echo %%P| findstr /I "WindowsApps" >nul
    if errorlevel 1 (
        start "" "%%P" "%~dp0main.py"
        exit /b
    )
)

echo.
echo Python 3 was not found. Install Python 3, or place YearProgress.exe
echo next to this script and run it again.
pause
