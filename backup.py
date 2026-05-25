"""
Config backup/restore for CheckPilot.
Export all settings to a single JSON file, import on new machine.
"""
import os
import json
import shutil
from datetime import datetime
from config import DATA_DIR

EXPORTABLE_FILES = [
    "schedule.json",
    "app_settings.json",
    "telegram.json",
    "licenses.db.json",
    "template_locks.json",
    "users.db.json",
]


def export_config(output_path: str) -> bool:
    """Export all config to a single JSON file."""
    try:
        bundle = {
            "exported_at": datetime.now().isoformat(),
            "version": "2.2.0",
            "configs": {},
        }

        for filename in EXPORTABLE_FILES:
            filepath = os.path.join(DATA_DIR, filename)
            if os.path.exists(filepath):
                with open(filepath, "r", encoding="utf-8") as f:
                    bundle["configs"][filename] = json.load(f)

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(bundle, f, indent=2, ensure_ascii=False)

        return True
    except Exception:
        return False


def import_config(input_path: str) -> tuple:
    """
    Import config from backup file.
    Returns (success, message, files_restored)
    """
    try:
        with open(input_path, "r", encoding="utf-8") as f:
            bundle = json.load(f)

        if "configs" not in bundle:
            return False, "Invalid backup file", 0

        os.makedirs(DATA_DIR, exist_ok=True)
        restored = 0

        for filename, data in bundle["configs"].items():
            if filename in EXPORTABLE_FILES:
                filepath = os.path.join(DATA_DIR, filename)
                with open(filepath, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=2, ensure_ascii=False)
                restored += 1

        return True, f"Restored {restored} config files", restored
    except Exception as e:
        return False, str(e), 0


def get_backup_info(filepath: str) -> dict:
    """Read backup file metadata without importing."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            bundle = json.load(f)
        return {
            "exported_at": bundle.get("exported_at", "Unknown"),
            "version": bundle.get("version", "Unknown"),
            "files": list(bundle.get("configs", {}).keys()),
        }
    except:
        return {}
