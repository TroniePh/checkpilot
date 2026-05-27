"""
Scheduler for CheckPilot.
Supports:
- Multiple run times per day (e.g. 08:00, 14:00, 20:00)
- Custom schedule (specific days/times)
- Background/tray mode
"""
import os
import json
import time
import threading
import logging
from datetime import datetime, timedelta
from typing import Callable, Optional, List

from config import DATA_DIR

logger = logging.getLogger(__name__)

SCHEDULE_FILE = os.path.join(DATA_DIR, "schedule.json")
DAY_MAP = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}
DEFAULT_MISSED_GRACE_MINUTES = 180


def load_schedule() -> dict:
    """Load saved schedule config."""
    if os.path.exists(SCHEDULE_FILE):
        with open(SCHEDULE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # Migration: convert old single "time" to "times" list
        if "time" in data and "times" not in data:
            data["times"] = [data.pop("time")]
        return data
    return {
        "enabled": False,
        "times": ["05:00"],
        "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "auto_date_today": True,
        "missed_grace_minutes": DEFAULT_MISSED_GRACE_MINUTES,
        "runs_today": [],
    }


def save_schedule(config: dict):
    """Save schedule config."""
    os.makedirs(DATA_DIR, exist_ok=True)
    # Keep backward compat: also store "time" as first entry
    if "times" in config and config["times"]:
        config["time"] = config["times"][0]
    with open(SCHEDULE_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2, ensure_ascii=False)


def _valid_times(config: dict) -> List[str]:
    values = config.get("times", [])
    if isinstance(values, str):
        values = [values]
    clean = []
    for value in values:
        try:
            hour, minute = map(int, str(value).split(":"))
            if 0 <= hour <= 23 and 0 <= minute <= 59:
                clean.append(f"{hour:02d}:{minute:02d}")
        except Exception:
            continue
    return sorted(set(clean))


def _reset_runs_if_new_day(config: dict, now: Optional[datetime] = None) -> list:
    now = now or datetime.now()
    runs_today = config.get("runs_today", [])
    if runs_today:
        try:
            last_date = runs_today[0].split("T")[0] if "T" in runs_today[0] else runs_today[0][:10]
            if last_date != now.date().isoformat():
                config["runs_today"] = []
                runs_today = []
        except Exception:
            config["runs_today"] = []
            runs_today = []
    return runs_today


def _missed_grace_minutes(config: dict) -> int:
    try:
        value = int(config.get("missed_grace_minutes", DEFAULT_MISSED_GRACE_MINUTES))
    except Exception:
        value = DEFAULT_MISSED_GRACE_MINUTES
    return max(0, min(value, 24 * 60))


def is_schedule_due_now(config: dict, now: Optional[datetime] = None) -> tuple:
    """Return (due, scheduled_time, reason) for current or recently missed slots."""
    now = now or datetime.now()
    if not config.get("enabled", False):
        return False, "", "schedule disabled"
    today_short = list(DAY_MAP.keys())[now.weekday()]
    if today_short not in config.get("days", []):
        return False, "", "today not selected"

    runs_today = _reset_runs_if_new_day(config, now)
    current_time = now.strftime("%H:%M")
    times = _valid_times(config)
    if current_time in times:
        time_key = f"{now.date().isoformat()}T{current_time}"
        if time_key in runs_today:
            return False, current_time, "already ran"
        return True, current_time, "due"

    grace = _missed_grace_minutes(config)
    if grace <= 0:
        return False, "", "not scheduled minute"

    missed = []
    for value in times:
        hour, minute = map(int, value.split(":"))
        target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if target > now:
            continue
        if now - target > timedelta(minutes=grace):
            continue
        time_key = f"{now.date().isoformat()}T{value}"
        if time_key not in runs_today:
            missed.append((target, value))

    if missed:
        _, scheduled_time = max(missed, key=lambda item: item[0])
        return True, scheduled_time, "missed"
    return False, "", "not scheduled minute"


def mark_schedule_run(config: dict, scheduled_time: str, now: Optional[datetime] = None):
    """Mark a schedule slot as triggered for today."""
    now = now or datetime.now()
    runs_today = _reset_runs_if_new_day(config, now)
    time_key = f"{now.date().isoformat()}T{scheduled_time}"
    if time_key not in runs_today:
        runs_today.append(time_key)
    config["runs_today"] = runs_today
    save_schedule(config)


def get_next_run_datetime(config: dict, now: Optional[datetime] = None) -> Optional[datetime]:
    """Return the next scheduled datetime, or None if schedule is not runnable."""
    now = now or datetime.now()
    if not config.get("enabled"):
        return None
    active_days = [DAY_MAP[d] for d in config.get("days", []) if d in DAY_MAP]
    if not active_days:
        return None
    times = _valid_times(config)
    if not times:
        return None
    for offset in range(8):
        check_date = now + timedelta(days=offset)
        if check_date.weekday() not in active_days:
            continue
        for value in times:
            hour, minute = map(int, value.split(":"))
            target = check_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target > now:
                return target
    return None


class Scheduler:
    """Background scheduler that triggers automation at configured times."""

    def __init__(self, run_callback: Callable[[], None], log_callback: Optional[Callable[[str], None]] = None):
        self.run_callback = run_callback
        self.log_callback = log_callback or (lambda msg: None)
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self.config = load_schedule()

    def start(self):
        """Start the scheduler background thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        times_str = ", ".join(self.config.get("times", []))
        self._log(f"Scheduler started - run at [{times_str}]")

    def stop(self):
        """Stop the scheduler."""
        self._running = False
        self._log("Scheduler stopped")

    def update_config(self, config: dict):
        """Update and save schedule config."""
        self.config = config
        save_schedule(config)
        times_str = ", ".join(config.get("times", []))
        self._log(f"Schedule updated: [{times_str}] | Days: {', '.join(config['days'])}")

    def is_running(self) -> bool:
        return self._running

    def _loop(self):
        """Main scheduler loop - check every 30 seconds."""
        while self._running:
            try:
                if self.config.get("enabled", False):
                    self._check_trigger()
            except Exception as e:
                logger.exception("Scheduler error")
                self._log(f"Scheduler error: {str(e)}")
            time.sleep(30)  # Check every 30 seconds

    def _check_trigger(self):
        """Check if it's time to run (supports multiple times per day)."""
        now = datetime.now()
        due, scheduled_time, reason = is_schedule_due_now(self.config, now)
        if not due:
            save_schedule(self.config)
            return

        if reason == "missed":
            self._log(f"Missed schedule {scheduled_time}; running catch-up at {now.strftime('%H:%M')}")
        else:
            self._log(f"Scheduled run triggered at {now.strftime('%H:%M')}")
        mark_schedule_run(self.config, scheduled_time, now)
        try:
            self.run_callback()
        except Exception as e:
            self._log(f"Scheduled run failed: {str(e)}")

    def get_next_run(self) -> str:
        """Get estimated next run time."""
        if not self.config.get("enabled"):
            return "Chưa bật"

        now = datetime.now()
        times = _valid_times(self.config)
        if not times:
            return "Chưa cài giờ"

        active_days = [DAY_MAP[d] for d in self.config.get("days", []) if d in DAY_MAP]

        if not active_days:
            return "Không có ngày nào được chọn"

        target = get_next_run_datetime(self.config, now)
        if target:
            return target.strftime("%d/%m/%Y %H:%M")

        return "N/A"

    def get_all_times_display(self) -> str:
        """Get formatted string of all scheduled times."""
        times = _valid_times(self.config)
        if not times:
            return "Chưa cài"
        return " | ".join(times)

    def _log(self, msg: str):
        logger.info(msg)
        self.log_callback(msg)
