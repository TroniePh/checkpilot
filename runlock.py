"""
Daily run lock — prevents duplicate submissions.
Tracks which inspections have been completed today.
"""
import os
import json
from datetime import date
from typing import List
from config import DATA_DIR

LOCK_FILE = os.path.join(DATA_DIR, "daily_runs.json")


def _load() -> dict:
    if os.path.exists(LOCK_FILE):
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save(data: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LOCK_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def _today_key() -> str:
    return date.today().isoformat()


def is_already_run_today(template: str, site: str) -> bool:
    """Check if this inspection was already completed today."""
    data = _load()
    today = _today_key()
    runs = data.get(today, [])
    key = f"{template}|{site}"
    return key in runs


def mark_completed(template: str, site: str):
    """Mark inspection as completed today."""
    data = _load()
    today = _today_key()
    if today not in data:
        data[today] = []
    key = f"{template}|{site}"
    if key not in data[today]:
        data[today].append(key)
    # Clean old entries (keep last 7 days)
    all_dates = sorted(data.keys(), reverse=True)
    for old_date in all_dates[7:]:
        del data[old_date]
    _save(data)


def get_today_completed() -> List[str]:
    """Get list of completed inspections today."""
    data = _load()
    return data.get(_today_key(), [])


def reset_today():
    """Clear today's lock (for manual re-run)."""
    data = _load()
    today = _today_key()
    if today in data:
        del data[today]
    _save(data)


def get_remaining(inspections_list: list) -> list:
    """Filter out already-completed inspections. Returns remaining."""
    completed = get_today_completed()
    remaining = []
    for insp in inspections_list:
        key = f"{insp.template_name}|{insp.site_location}"
        if key not in completed:
            remaining.append(insp)
    return remaining
