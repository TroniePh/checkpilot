"""
Single instance lock — prevents running multiple copies of CheckPilot.
Uses a lock file with PID check.
"""
import os
import sys
import logging
from config import DATA_DIR

logger = logging.getLogger(__name__)
LOCK_FILE = os.path.join(DATA_DIR, ".app.lock")


def is_already_running() -> bool:
    """Check if another instance is running. Returns True if locked."""
    os.makedirs(DATA_DIR, exist_ok=True)

    if not os.path.exists(LOCK_FILE):
        return False

    # Read PID from lock file
    try:
        with open(LOCK_FILE, "r") as f:
            pid = int(f.read().strip())
    except (ValueError, IOError):
        # Corrupt lock file — remove it
        _remove_lock()
        return False

    # Check if that PID is still alive
    if _pid_alive(pid):
        return True
    else:
        # Stale lock (process crashed) — remove it
        logger.info(f"Stale lock found (PID {pid} dead). Removing.")
        _remove_lock()
        return False


def acquire_lock() -> bool:
    """Acquire the lock. Returns True if successful."""
    if is_already_running():
        return False

    os.makedirs(DATA_DIR, exist_ok=True)
    try:
        with open(LOCK_FILE, "w") as f:
            f.write(str(os.getpid()))
        return True
    except IOError:
        return False


def release_lock():
    """Release the lock on exit."""
    _remove_lock()


def _remove_lock():
    try:
        if os.path.exists(LOCK_FILE):
            os.remove(LOCK_FILE)
    except:
        pass


def _pid_alive(pid: int) -> bool:
    """Check if a process with given PID is running."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
            if handle:
                kernel32.CloseHandle(handle)
                return True
            return False
        except:
            return False
    else:
        # Unix
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False
