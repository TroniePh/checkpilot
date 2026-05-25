"""
Template lock — requires test run before allowing auto-submit.
Prevents accidental submission of untested templates.
"""
import os
import json
from datetime import datetime
from typing import Optional
from config import DATA_DIR

LOCK_FILE = os.path.join(DATA_DIR, "template_locks.json")


def _load() -> dict:
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LOCK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def is_template_tested(template_name: str) -> bool:
    """Check if template has been successfully tested at least once."""
    data = _load()
    entry = data.get(template_name)
    if not entry:
        return False
    return entry.get("tested", False)


def mark_template_tested(template_name: str, items_count: int = 0):
    """Mark template as tested (after successful test run)."""
    data = _load()
    data[template_name] = {
        "tested": True,
        "tested_at": datetime.now().isoformat(),
        "items_count": items_count,
    }
    _save(data)


def get_all_locks() -> dict:
    """Get all template lock states."""
    return _load()


def reset_template(template_name: str):
    """Reset a template lock (require re-testing)."""
    data = _load()
    if template_name in data:
        del data[template_name]
    _save(data)


def reset_all():
    """Clear all template locks."""
    _save({})


def get_untested_templates(template_names: list) -> list:
    """Return list of templates that haven't been tested yet."""
    return [t for t in template_names if not is_template_tested(t)]
