"""Persist the currently running Auto Mode job for crash/power-loss resume."""
import json
import os
from datetime import date, datetime
from config import DATA_DIR


RUN_STATE_FILE = os.path.join(DATA_DIR, "run_state.json")


def _norm_path(path: str) -> str:
    if not path:
        return ""
    try:
        return os.path.normcase(os.path.abspath(path))
    except Exception:
        return path


def _write(state: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = RUN_STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
    os.replace(tmp, RUN_STATE_FILE)


def load_run_state() -> dict:
    if not os.path.exists(RUN_STATE_FILE):
        return {}
    try:
        with open(RUN_STATE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_run_state(**updates):
    state = load_run_state()
    state.update(updates)
    state["updated_at"] = datetime.now().isoformat()
    _write(state)


def start_run_state(
    data_file: str,
    image_folder: str,
    total: int,
    auto_submit: bool,
    scheduled: bool,
):
    _write({
        "status": "running",
        "date": date.today().isoformat(),
        "data_file": data_file,
        "data_file_norm": _norm_path(data_file),
        "image_folder": image_folder,
        "image_folder_norm": _norm_path(image_folder),
        "total": int(total or 0),
        "done": 0,
        "success": 0,
        "failed": 0,
        "current_index": 0,
        "current_template": "",
        "auto_submit": bool(auto_submit),
        "scheduled": bool(scheduled),
        "started_at": datetime.now().isoformat(),
        "updated_at": datetime.now().isoformat(),
    })


def update_run_state(**updates):
    state = load_run_state()
    if not state:
        return
    state.update(updates)
    state["updated_at"] = datetime.now().isoformat()
    _write(state)


def clear_run_state():
    try:
        if os.path.exists(RUN_STATE_FILE):
            os.remove(RUN_STATE_FILE)
    except OSError:
        pass


def is_interrupted_auto_run(state: dict, data_file: str = "") -> bool:
    if not state or state.get("status") != "running":
        return False
    if state.get("date") != date.today().isoformat():
        return False
    if not state.get("auto_submit"):
        return False
    if data_file and state.get("data_file_norm") != _norm_path(data_file):
        return False
    return True
