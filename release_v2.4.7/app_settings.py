"""Persistent app settings for CheckPilot."""
import json
import os
from typing import Any

from config import DATA_DIR


SETTINGS_FILE = os.path.join(DATA_DIR, "app_settings.json")


DEFAULT_SETTINGS = {
    "data_file": "",
    "image_folder": "",
    "auto_date_today": True,
    "template_folder_url": "",
}


def load_app_settings() -> dict:
    """Load app settings, returning defaults when missing or invalid."""
    if not os.path.exists(SETTINGS_FILE):
        return dict(DEFAULT_SETTINGS)
    try:
        with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        settings = dict(DEFAULT_SETTINGS)
        settings.update({k: v for k, v in data.items() if k in DEFAULT_SETTINGS})
        return settings
    except Exception:
        return dict(DEFAULT_SETTINGS)


def save_app_settings(**updates: Any) -> dict:
    """Update and save app settings."""
    settings = load_app_settings()
    for key, value in updates.items():
        if key in DEFAULT_SETTINGS:
            settings[key] = value
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)
    return settings
