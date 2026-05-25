@echo off
setlocal
echo === CheckPilot - Commercial Installer Build ===
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installer\build_release.ps1"
if errorlevel 1 (
  echo.
  echo === Build FAILED ===
  pause
  exit /b 1
)
echo.
echo === Build complete ===
echo Installer is in: release\
pause
