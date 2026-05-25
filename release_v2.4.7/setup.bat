@echo off
chcp 65001 >nul
title CheckPilot - Setup & Run
echo.
echo â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
echo â•‘   CheckPilotâ„¢ - Auto Setup              â•‘
echo â•‘   CÃ i Ä‘áº·t tá»± Ä‘á»™ng trong folder hiá»‡n táº¡i        â•‘
echo â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
echo.

:: Set all paths relative to this script's folder
set "APP_DIR=%~dp0"
cd /d "%APP_DIR%"

set "VENV_DIR=%APP_DIR%venv"
set "PW_BROWSERS=%APP_DIR%.browsers"
set "PLAYWRIGHT_BROWSERS_PATH=%PW_BROWSERS%"

echo [INFO] Working directory: %APP_DIR%
echo [INFO] Venv: %VENV_DIR%
echo [INFO] Browsers: %PW_BROWSERS%
echo.

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found! Please install Python 3.9+ first.
    echo         Download: https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Create virtual environment in project folder
if not exist "%VENV_DIR%\Scripts\activate.bat" (
    echo [1/4] Creating virtual environment...
    python -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [ERROR] Failed to create venv!
        pause
        exit /b 1
    )
    echo       Done.
) else (
    echo [1/4] Virtual environment already exists. OK.
)

:: Activate venv
call "%VENV_DIR%\Scripts\activate.bat"

:: Install Python packages
echo [2/4] Installing Python packages...
pip install --quiet --disable-pip-version-check -r "%APP_DIR%requirements.txt"
if errorlevel 1 (
    echo [ERROR] Failed to install packages!
    pause
    exit /b 1
)
echo       Done.

:: Install Playwright browser into project folder
if not exist "%PW_BROWSERS%\chromium-*" (
    echo [3/4] Installing Chromium browser (local to project)...
    set "PLAYWRIGHT_BROWSERS_PATH=%PW_BROWSERS%"
    playwright install chromium
    if errorlevel 1 (
        echo [ERROR] Failed to install browser!
        pause
        exit /b 1
    )
    echo       Done.
) else (
    echo [3/4] Chromium browser already installed. OK.
)

:: Create data directories
echo [4/4] Creating data directories...
if not exist "%APP_DIR%data" mkdir "%APP_DIR%data"
if not exist "%APP_DIR%screenshots" mkdir "%APP_DIR%screenshots"
if not exist "%APP_DIR%logs" mkdir "%APP_DIR%logs"
echo       Done.

echo.
echo â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—
echo â•‘   Setup complete! Starting application...       â•‘
echo â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•
echo.

:: Run the app
set "PLAYWRIGHT_BROWSERS_PATH=%PW_BROWSERS%"
python "%APP_DIR%main.py"

pause
