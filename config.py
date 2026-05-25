"""Configuration constants for CheckPilot."""
import os
import sys


def _install_dir() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


INSTALL_DIR = _install_dir()
BASE_DIR = getattr(sys, "_MEIPASS", INSTALL_DIR)

# Keep bundled browser next to the executable, but write client data to a
# per-user folder so the installed app works without administrator rights.
BROWSERS_DIR = os.path.join(BASE_DIR, ".browsers")
if getattr(sys, "frozen", False):
    RUNTIME_DIR = os.path.join(os.environ.get("LOCALAPPDATA", BASE_DIR), "CheckPilot")
else:
    RUNTIME_DIR = BASE_DIR

DATA_DIR = os.path.join(RUNTIME_DIR, "data")
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = BROWSERS_DIR

# Browser settings
BROWSER_HEADLESS = False
BROWSER_SLOW_MO = 100  # ms between actions
DEFAULT_TIMEOUT = 30000  # 30s timeout for elements
NAVIGATION_TIMEOUT = 60000  # 60s for page navigation

# SafetyCulture URLs
# Login redirects to app.safetyculture.com; use that as base.
SC_BASE_URL = "https://app.safetyculture.com"
SC_LOGIN_URL = "https://app.safetyculture.com/login"
SC_INSPECTIONS_URL = "https://app.safetyculture.com/inspections"
SC_TEMPLATES_URL = "https://app.safetyculture.com/templates/index"
SC_TEMPLATE_FOLDER_URL = os.environ.get("CHECKPILOT_TEMPLATE_FOLDER_URL", "").strip()
# Template folder name to navigate into (e.g. "Yummi Sushi - Daily Required Checklists")
SC_TEMPLATE_FOLDER_NAME = os.environ.get("CHECKPILOT_TEMPLATE_FOLDER", "").strip()

# Retry settings
MAX_RETRIES = 3
RETRY_DELAY = 2  # seconds

# Screenshot on error
SCREENSHOT_DIR = os.path.join(RUNTIME_DIR, "screenshots")
LOG_DIR = os.path.join(RUNTIME_DIR, "logs")

# Ensure directories exist
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
os.makedirs(LOG_DIR, exist_ok=True)
