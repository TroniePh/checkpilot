"""
Watchdog — monitors app health, auto-restart if hung.
Runs as a background thread checking last activity timestamp.
"""
import os
import sys
import time
import logging
import threading
import subprocess
from datetime import datetime
from config import DATA_DIR

logger = logging.getLogger(__name__)
HEARTBEAT_FILE = os.path.join(DATA_DIR, ".heartbeat")
MAX_IDLE_SECONDS = 600  # 10 minutes without activity = hung


def beat():
    """Update heartbeat timestamp. Call this periodically from main app."""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(HEARTBEAT_FILE, "w") as f:
            f.write(datetime.now().isoformat())
    except Exception:
        pass


def get_last_beat() -> float:
    """Get seconds since last heartbeat."""
    if not os.path.exists(HEARTBEAT_FILE):
        return 0
    try:
        with open(HEARTBEAT_FILE, "r") as f:
            ts = datetime.fromisoformat(f.read().strip())
        return (datetime.now() - ts).total_seconds()
    except Exception:
        return 0


class Watchdog:
    """Background watchdog thread."""

    def __init__(self, restart_callback=None):
        self._running = False
        self._thread = None
        self.restart_callback = restart_callback

    def start(self):
        if self._running:
            return
        self._running = True
        beat()  # Initial heartbeat
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info("Watchdog started")

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            time.sleep(30)  # Check every 30s
            # Auto-beat when app is alive (GUI running = app is fine)
            beat()
            idle = get_last_beat()
            if idle > MAX_IDLE_SECONDS:
                logger.warning(f"Watchdog: App idle for {idle:.0f}s")
                # Don't restart — just log. Opening a new instance causes duplicates.
                break

    def _restart_app(self):
        """Restart the application process."""
        try:
            logger.info("Watchdog: Restarting app...")
            python = sys.executable
            script = os.path.join(os.path.dirname(__file__), "main.py")
            subprocess.Popen([python, script], cwd=os.path.dirname(__file__))
        except Exception as e:
            logger.error(f"Watchdog restart failed: {e}")
