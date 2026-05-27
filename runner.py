"""Headless CheckPilot runner for Windows Task Scheduler.

The GUI cannot run before Windows login because there is no interactive
desktop session. This runner is intentionally headless and can be started by
Task Scheduler at boot, then wait for the configured schedule.
"""
import argparse
import logging
import os
import sys
import time
from datetime import date, datetime
from typing import Optional

from automation import AutomationEngine
from autostart import (
    build_validation_state,
    get_last_data_file,
    get_last_image_folder,
    get_validation_state,
    is_validation_current,
    save_validation_state,
)
from config import DATA_DIR, LOG_DIR
from data_loader import load_data, validate_detailed
from history import add_record
from notifier import send_daily_summary, send_error_alert
from reporter import generate_report
from runlock import get_remaining, mark_completed
from run_state import (
    clear_run_state,
    is_interrupted_auto_run,
    load_run_state,
    start_run_state,
    update_run_state,
)
from scheduler import (
    get_next_run_datetime,
    is_schedule_due_now,
    load_schedule,
    mark_schedule_run,
)
from session_manager import has_saved_credentials, has_saved_session
from singleton import acquire_lock, release_lock
from template_lock import get_invalid_templates


logger = logging.getLogger(__name__)
RUNNER_LOCK_FILE = os.path.join(DATA_DIR, ".runner.lock")
MAX_CONSECUTIVE_FAILURES = 3


def _setup_logging():
    if logging.getLogger().handlers:
        return
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"runner_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


def _log(msg: str):
    logger.info(msg)


def _pid_alive(pid: int) -> bool:
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def acquire_runner_lock() -> bool:
    os.makedirs(DATA_DIR, exist_ok=True)
    if os.path.exists(RUNNER_LOCK_FILE):
        try:
            with open(RUNNER_LOCK_FILE, "r", encoding="utf-8") as f:
                pid = int(f.read().strip())
            if _pid_alive(pid):
                return False
        except Exception:
            pass
        try:
            os.remove(RUNNER_LOCK_FILE)
        except OSError:
            pass
    try:
        with open(RUNNER_LOCK_FILE, "w", encoding="utf-8") as f:
            f.write(str(os.getpid()))
        return True
    except OSError:
        return False


def release_runner_lock():
    try:
        if os.path.exists(RUNNER_LOCK_FILE):
            os.remove(RUNNER_LOCK_FILE)
    except OSError:
        pass


def _validation_error_message(report: dict) -> str:
    lines = []
    if report.get("errors"):
        lines.append("Validation errors:")
        lines.extend(f"- {e}" for e in report["errors"][:8])
    if report.get("warnings"):
        lines.append("Validation warnings:")
        lines.extend(f"- {w}" for w in report["warnings"][:8])
    return "\n".join(lines) or "Validation failed"


def _validate_inputs(data_file: str, image_folder: str) -> tuple:
    if not data_file:
        return False, "Chưa cấu hình file CSV/Excel.", None
    if not os.path.exists(data_file):
        return False, f"File dữ liệu không tồn tại: {data_file}", None

    report = validate_detailed(data_file, image_folder)
    if report.get("errors"):
        return False, _validation_error_message(report), report

    missing_images = report.get("stats", {}).get("images_missing", 0)
    if missing_images:
        state = get_validation_state()
        if not is_validation_current(data_file, image_folder, state):
            msg = (
                "Có ảnh không tìm thấy. Runner nền không được hiện popup xác nhận.\n"
                "Mở CheckPilot, bấm Validate và xác nhận tiếp tục trước khi chạy lịch."
            )
            return False, msg, report

    if not missing_images:
        save_validation_state(build_validation_state(data_file, image_folder, True, 0, False))
    return True, "OK", report


def _prepare_inspections(data_file: str, image_folder: str) -> list:
    inspections = load_data(data_file, image_folder)
    today = date.today().isoformat()
    for insp in inspections:
        insp.inspection_date = today
    return inspections


def _send_blocking_error(message: str, screenshot: Optional[str] = None):
    _log(message)
    send_error_alert(message, screenshot)


def execute_auto_run() -> bool:
    """Run all due inspections in Auto Mode. Returns True when all run OK."""
    data_file = get_last_data_file()
    image_folder = get_last_image_folder()

    ok, msg, _ = _validate_inputs(data_file, image_folder)
    if not ok:
        _send_blocking_error(msg)
        return False

    if not has_saved_session() and not has_saved_credentials():
        _send_blocking_error(
            "Runner nền cần SafetyCulture session hoặc credentials đã lưu. "
            "Mở CheckPilot một lần, đăng nhập SafetyCulture và lưu credentials."
        )
        return False

    try:
        inspections = _prepare_inspections(data_file, image_folder)
    except Exception as e:
        _send_blocking_error(f"Không load được dữ liệu: {e}")
        return False

    invalid_templates = get_invalid_templates(inspections)
    if invalid_templates:
        _log(
            "WARN: Template locks are not current; runner continues after validation OK:\n" +
            "\n".join(f"- {t}" for t in invalid_templates)
        )

    run_list = get_remaining(inspections)
    skipped = len(inspections) - len(run_list)
    if not run_list:
        _log("Không còn inspection cần chạy hôm nay.")
        send_daily_summary(total=0, success=0, failed=0, skipped=skipped)
        return True

    if not acquire_lock():
        _send_blocking_error("CheckPilot GUI/automation khác đang chạy. Runner bỏ qua để tránh submit trùng.")
        return False

    engine = AutomationEngine(log_callback=_log, force_headless=True, allow_manual_login=False)
    total = len(run_list)
    success = 0
    failed = 0
    consecutive_failures = 0
    recent_errors = []
    start_run_state(
        data_file=data_file,
        image_folder=image_folder,
        total=total,
        auto_submit=True,
        scheduled=True,
    )

    try:
        engine.start_browser()
        engine.wait_for_login()

        _log("Running health check...")
        hc_ok, hc_msg = engine.health_check()
        if not hc_ok:
            screenshot = engine._screenshot_error("runner_health_check_failed")
            failed = total
            _send_blocking_error(f"Health check failed: {hc_msg}", screenshot)
            return False

        for idx, insp in enumerate(run_list, 1):
            _log(f"[{idx}/{total}] AUTO: {insp.template_name} | {insp.site_location}")
            update_run_state(
                status="running",
                current_index=idx,
                current_template=insp.template_name,
                total=total,
                done=idx - 1,
                success=success,
                failed=failed,
            )
            started = datetime.now()
            ok = engine.run_inspection(insp, auto_submit=True)
            errors = []
            if ok:
                consecutive_failures = 0
                if not engine.verify_inspection_saved(insp.template_name):
                    _log("Submitted but not verified in list yet")
                mark_completed(insp.template_name, insp.site_location)
                success += 1
            else:
                errors = engine.item_errors or [f"Failed: {insp.template_name}"]
                recent_errors.extend(errors)
                failed += 1
                consecutive_failures += 1

            add_record(
                insp.template_name,
                insp.site_location,
                insp.inspection_date,
                len(insp.items),
                ok,
                errors,
                data_file,
            )
            duration_sec = (datetime.now() - started).total_seconds()
            img_total = sum(len(it.image_paths) for it in insp.items)
            generate_report(
                template=insp.template_name,
                site=insp.site_location,
                inspection_date=insp.inspection_date,
                total_items=len(insp.items),
                items_ok=getattr(engine, "_items_ok", max(0, len(insp.items) - len(errors))),
                items_failed=len(engine.item_errors),
                errors=engine.item_errors,
                images_uploaded=getattr(engine, "_images_uploaded", max(0, img_total)),
                images_failed=getattr(engine, "_images_failed", 0),
                submitted=ok,
                mode="auto",
                duration_sec=duration_sec,
                data_file=data_file,
            )
            update_run_state(
                status="running",
                current_index=idx,
                current_template=insp.template_name,
                total=total,
                done=idx,
                success=success,
                failed=failed,
            )

            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                msg = (
                    f"Auto Mode stopped after {consecutive_failures} consecutive failures. "
                    "No more inspections will run until this is checked."
                )
                _log(msg)
                screenshot = None
                try:
                    screenshot = engine._screenshot_error("runner_consecutive_failures")
                except Exception:
                    pass
                send_error_alert(
                    msg, screenshot, insp.template_name, insp.site_location,
                    question=getattr(engine, "current_question", ""),
                    url=engine.page.url if engine.page else "",
                    details=recent_errors[-8:],
                )
                update_run_state(status="blocked")
                break

        return failed == 0
    except Exception as e:
        failed = max(failed, total - success)
        screenshot = None
        try:
            screenshot = engine._screenshot_error("runner_fatal")
        except Exception:
            pass
        _send_blocking_error(f"Runner fatal: {e}", screenshot)
        logger.exception("Runner fatal")
        return False
    finally:
        try:
            send_daily_summary(total=total, success=success, failed=failed, skipped=skipped)
        except Exception:
            pass
        try:
            engine.close_browser()
        except Exception:
            pass
        clear_run_state()
        release_lock()


def run_if_due(force: bool = False, quiet: bool = False) -> Optional[bool]:
    state = load_run_state()
    data_file = get_last_data_file()
    if is_interrupted_auto_run(state, data_file):
        _log("Phát hiện Auto run bị gián đoạn. Runner chạy tiếp phần còn lại.")
        return execute_auto_run()

    schedule = load_schedule()
    if not force:
        due, scheduled_time, reason = is_schedule_due_now(schedule)
        if not due:
            if not quiet:
                target = get_next_run_datetime(schedule)
                if target:
                    _log(f"Chưa tới giờ chạy ({reason}). Chờ tới {target.strftime('%d/%m/%Y %H:%M')}.")
                else:
                    _log(f"Không có lịch hợp lệ ({reason}).")
            return None
        if reason == "missed":
            _log(f"Missed schedule {scheduled_time}; running catch-up Auto Mode.")
        else:
            _log(f"Đúng lịch {scheduled_time}. Bắt đầu Auto Mode.")
        mark_schedule_run(schedule, scheduled_time)
    else:
        _log("Force run: bỏ qua kiểm tra giờ lịch.")
    return execute_auto_run()


def status() -> int:
    schedule = load_schedule()
    target = get_next_run_datetime(schedule)
    _log(f"Data file: {get_last_data_file() or '(chưa cấu hình)'}")
    _log(f"Image folder: {get_last_image_folder() or '(chưa cấu hình)'}")
    _log(f"Schedule enabled: {bool(schedule.get('enabled'))}")
    _log(f"Next run: {target.strftime('%d/%m/%Y %H:%M') if target else 'N/A'}")
    _log(f"Saved SC session: {has_saved_session()}")
    _log(f"Saved SC credentials: {has_saved_credentials()}")
    return 0


def main(argv=None) -> int:
    _setup_logging()
    parser = argparse.ArgumentParser(description="CheckPilot headless runner")
    parser.add_argument("--watch", action="store_true", help="wait forever and run when schedule is due")
    parser.add_argument("--once", action="store_true", help="check schedule once and exit")
    parser.add_argument("--force", action="store_true", help="run immediately, bypassing schedule time")
    parser.add_argument("--status", action="store_true", help="print runner status and exit")
    args = parser.parse_args(argv)

    if args.status:
        return status()

    if not acquire_runner_lock():
        _log("Runner đã chạy ở tiến trình khác.")
        return 0

    try:
        if args.watch:
            _log("Runner watch started. Waiting for schedule.")
            target = get_next_run_datetime(load_schedule())
            if target:
                _log(f"Next run: {target.strftime('%d/%m/%Y %H:%M')}")
            while True:
                run_if_due(force=False, quiet=True)
                time.sleep(30)
        result = run_if_due(force=args.force)
        if result is None:
            return 0
        return 0 if result else 1
    finally:
        release_runner_lock()


if __name__ == "__main__":
    raise SystemExit(main())
