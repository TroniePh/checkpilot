#!/bin/bash
echo "=== CheckPilot - Build Script (Mac/Linux) ==="
echo

echo "[1/3] Installing dependencies..."
pip install -r requirements.txt || { echo "FAILED"; exit 1; }

echo "[2/3] Installing Playwright browser..."
playwright install chromium || { echo "FAILED"; exit 1; }

echo "[3/3] Building executable..."
pip install pyinstaller
pyinstaller --onefile --windowed --name SafetyCultureAuto --add-data "sample_data.csv:." main.py || { echo "FAILED"; exit 1; }

echo
echo "=== Build complete! ==="
echo "Executable: dist/SafetyCultureAuto"
