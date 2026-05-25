"""
Auto-start configuration for CheckPilot.
- Saves last used data file + image folder
- Auto-loads on startup
- Registers app to run on Windows startup (optional)
"""
import os
import sys
import json
import logging
from config import DATA_DIR

logger = logging.getLogger(__name__)
AUTOSTART_CONFIG = os.path.join(DATA_DIR, "autostart.json")


def save_last_config(data_file: str, image_folder: str):
    """Save last used file paths for auto-reload."""
    os.makedirs(DATA_DIR, exist_ok=True)
    cfg = load_autostart_config()
    cfg["last_data_file"] = data_file
    cfg["last_image_folder"] = image_folder
    with open(AUTOSTART_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def load_autostart_config() -> dict:
    """Load auto-start config."""
    if os.path.exists(AUTOSTART_CONFIG):
        with open(AUTOSTART_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "last_data_file": "",
        "last_image_folder": "",
        "auto_load_on_start": True,
        "run_on_windows_startup": False,
        "template_folder_name": "Yummi Sushi - Daily Required Checklists",
        "template_folder_url": "",
    }


def save_autostart_config(cfg: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(AUTOSTART_CONFIG, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def get_last_data_file() -> str:
    return load_autostart_config().get("last_data_file", "")


def get_last_image_folder() -> str:
    return load_autostart_config().get("last_image_folder", "")


def register_windows_startup(enable: bool = True):
    """Add/remove app from Windows startup registry."""
    if sys.platform != "win32":
        return

    import winreg
    key_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "CheckPilot"

    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0, winreg.KEY_SET_VALUE)
        if enable:
            # Get the path to run
            script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
            python = sys.executable
            cmd = f'"{python}" "{script}"'
            winreg.SetValueEx(key, app_name, 0, winreg.REG_SZ, cmd)
            logger.info("Registered for Windows startup")
        else:
            try:
                winreg.DeleteValue(key, app_name)
                logger.info("Removed from Windows startup")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
    except Exception as e:
        logger.warning(f"Startup registry error: {e}")


def is_registered_startup() -> bool:
    """Check if app is in Windows startup."""
    if sys.platform != "win32":
        return False
    import winreg
    try:
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                             r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_READ)
        winreg.QueryValueEx(key, "CheckPilot")
        winreg.CloseKey(key)
        return True
    except:
        return False
