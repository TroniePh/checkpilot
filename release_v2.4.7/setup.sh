#!/bin/bash
# CheckPilotâ„¢ - Auto Setup & Run (Mac/Linux)
# Táº¥t cáº£ cÃ i Ä‘áº·t trong folder hiá»‡n táº¡i, khÃ´ng áº£nh hÆ°á»Ÿng há»‡ thá»‘ng

echo ""
echo "â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—"
echo "â•‘   CheckPilotâ„¢ - Auto Setup              â•‘"
echo "â•‘   CÃ i Ä‘áº·t tá»± Ä‘á»™ng trong folder hiá»‡n táº¡i        â•‘"
echo "â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•"
echo ""

# Set paths relative to script location
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

VENV_DIR="$APP_DIR/venv"
PW_BROWSERS="$APP_DIR/.browsers"

export PLAYWRIGHT_BROWSERS_PATH="$PW_BROWSERS"

echo "[INFO] Working directory: $APP_DIR"
echo "[INFO] Venv: $VENV_DIR"
echo "[INFO] Browsers: $PW_BROWSERS"
echo ""

# Check Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python3 not found! Install Python 3.9+ first."
    exit 1
fi

# Create virtual environment
if [ ! -f "$VENV_DIR/bin/activate" ]; then
    echo "[1/4] Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to create venv!"
        exit 1
    fi
    echo "      Done."
else
    echo "[1/4] Virtual environment already exists. OK."
fi

# Activate venv
source "$VENV_DIR/bin/activate"

# Install packages
echo "[2/4] Installing Python packages..."
pip install --quiet --disable-pip-version-check -r "$APP_DIR/requirements.txt"
if [ $? -ne 0 ]; then
    echo "[ERROR] Failed to install packages!"
    exit 1
fi
echo "      Done."

# Install browser
if [ ! -d "$PW_BROWSERS" ] || [ -z "$(ls -A "$PW_BROWSERS" 2>/dev/null)" ]; then
    echo "[3/4] Installing Chromium browser (local to project)..."
    playwright install chromium
    if [ $? -ne 0 ]; then
        echo "[ERROR] Failed to install browser!"
        exit 1
    fi
    echo "      Done."
else
    echo "[3/4] Chromium browser already installed. OK."
fi

# Create directories
echo "[4/4] Creating data directories..."
mkdir -p "$APP_DIR/data"
mkdir -p "$APP_DIR/screenshots"
mkdir -p "$APP_DIR/logs"
echo "      Done."

echo ""
echo "â•”â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•—"
echo "â•‘   Setup complete! Starting application...       â•‘"
echo "â•šâ•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•â•"
echo ""

# Run
python "$APP_DIR/main.py"
