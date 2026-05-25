"""Entry point for CheckPilot / Inspection Automation Assistant."""
import sys
import os
import logging
import atexit
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import LOG_DIR

# Setup logging
log_file = os.path.join(LOG_DIR, f"session_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(),
    ],
)

logger = logging.getLogger(__name__)


def main():
    """Launch the application."""
    if "--runner" in sys.argv:
        from runner import main as runner_main
        runner_args = [arg for arg in sys.argv[1:] if arg != "--runner"]
        raise SystemExit(runner_main(runner_args))

    logger.info("CheckPilot starting...")

    # Single instance check
    from singleton import acquire_lock, release_lock
    if not acquire_lock():
        logger.warning("Another instance is already running!")
        # Show message box without full GUI
        try:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showwarning(
                "CheckPilot",
                "Phần mềm đang chạy ở tiến trình khác.\n"
                "Kiểm tra system tray hoặc Task Manager."
            )
            root.destroy()
        except:
            print("CheckPilot is already running!")
        sys.exit(0)

    # Release lock on exit
    atexit.register(release_lock)

    try:
        # Start watchdog
        from watchdog import Watchdog
        wd = Watchdog()
        wd.start()

        from gui import main as gui_main
        gui_main()
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        print(f"\nMissing dependency: {e}")
        print("Run: pip install -r requirements.txt")
        release_lock()
        sys.exit(1)
    except Exception as e:
        logger.exception("Application crashed")
        print(f"\nError: {e}")
        release_lock()
        sys.exit(1)
    finally:
        release_lock()


if __name__ == "__main__":
    main()
