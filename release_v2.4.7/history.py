"""Run history tracking and export for CheckPilot."""
import os
import json
import csv
from datetime import datetime
from typing import List
from config import DATA_DIR

HISTORY_FILE = os.path.join(DATA_DIR, "history.json")


def _load() -> List[dict]:
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save(data: List[dict]):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def add_record(template: str, site: str, date_str: str, items: int,
               success: bool, errors: List[str] = None, data_file: str = ""):
    """Add a run record."""
    records = _load()
    records.insert(0, {
        "timestamp": datetime.now().isoformat(),
        "template": template,
        "site": site,
        "inspection_date": date_str,
        "items": items,
        "success": success,
        "errors": errors or [],
        "data_file": os.path.basename(data_file) if data_file else "",
    })
    # Keep last 500 records
    records = records[:500]
    _save(records)


def get_records(limit: int = 50) -> List[dict]:
    """Get recent records."""
    return _load()[:limit]


def get_stats() -> dict:
    """Get summary stats."""
    records = _load()
    total = len(records)
    success = sum(1 for r in records if r.get("success"))
    failed = total - success
    today = datetime.now().date().isoformat()
    today_count = sum(1 for r in records if r.get("timestamp", "").startswith(today))
    return {
        "total": total,
        "success": success,
        "failed": failed,
        "today": today_count,
    }


def export_csv(filepath: str) -> bool:
    """Export history to CSV."""
    records = _load()
    if not records:
        return False
    try:
        with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "timestamp", "template", "site", "inspection_date",
                "items", "success", "errors", "data_file"
            ])
            writer.writeheader()
            for r in records:
                row = dict(r)
                row["errors"] = "; ".join(row.get("errors", []))
                writer.writerow(row)
        return True
    except Exception:
        return False
