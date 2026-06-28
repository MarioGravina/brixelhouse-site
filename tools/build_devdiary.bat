@echo off
setlocal

set REPO_DIR=C:\dev\brixelhouse-site

cd /d "%REPO_DIR%"

echo.
echo === Building Brixel House Dev Diary ===
echo.

python tools\build_devdiary.py --repo "%REPO_DIR%"

if errorlevel 1 (
    echo.
    echo Build failed.
    pause
    exit /b 1
)

echo.
echo Build completed.
echo Preview with Live Server, then commit/push when ready.
echo.
pause
exit /b 0