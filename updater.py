"""
Auto-update system for CheckPilot.
Checks remote version, downloads installer, and performs silent upgrade.
"""
import os
import sys
import json
import logging
import tempfile
import subprocess
import threading
import requests
from datetime import datetime, timedelta
from typing import Tuple, Optional, Callable
from config import DATA_DIR, INSTALL_DIR

logger = logging.getLogger(__name__)

CURRENT_VERSION = "2.4.5"
# Update URL — host file version.json ở đây (GitHub raw, server riêng, etc.)
VERSION_CHECK_URL = "https://raw.githubusercontent.com/TroniePh/checkpilot/main/version.json"
UPDATE_CHECK_FILE = os.path.join(DATA_DIR, "last_update_check.json")
UPDATE_DOWNLOAD_DIR = os.path.join(DATA_DIR, "updates")


def get_current_version() -> str:
    return CURRENT_VERSION


def check_for_update(force: bool = False) -> Tuple[bool, Optional[str], Optional[str], Optional[str]]:
    """
    Check if newer version available.
    Returns: (update_available, latest_version, download_url, changelog)
    """
    if not force and _checked_recently():
        return False, None, None, None

    try:
        resp = requests.get(VERSION_CHECK_URL, timeout=10)
        if resp.status_code != 200:
            return False, None, None, None

        data = resp.json()
        latest = data.get("version", CURRENT_VERSION)
        download_url = data.get("download_url", "")
        changelog = data.get("changelog", "")
        mandatory = data.get("mandatory", False)

        _save_check_time()

        if _version_newer(latest, CURRENT_VERSION):
            return True, latest, download_url, changelog

        return False, latest, None, None

    except Exception as e:
        logger.debug(f"Update check failed: {e}")
        return False, None, None, None


def download_update(url: str, progress_callback: Optional[Callable[[float], None]] = None) -> Optional[str]:
    """
    Download the installer from url.
    progress_callback receives float 0.0 - 1.0.
    Returns path to downloaded file, or None on failure.
    """
    os.makedirs(UPDATE_DOWNLOAD_DIR, exist_ok=True)

    # Extract filename from URL
    filename = url.split("/")[-1]
    if not filename.endswith(".exe"):
        filename = "CheckPilot_Update.exe"

    dest_path = os.path.join(UPDATE_DOWNLOAD_DIR, filename)

    # Remove old download if exists
    if os.path.exists(dest_path):
        try:
            os.remove(dest_path)
        except OSError:
            pass

    try:
        resp = requests.get(url, stream=True, timeout=300)
        resp.raise_for_status()

        total_size = int(resp.headers.get("content-length", 0))
        downloaded = 0
        chunk_size = 8192

        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=chunk_size):
                if chunk:
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total_size > 0:
                        progress_callback(downloaded / total_size)

        # Final progress
        if progress_callback:
            progress_callback(1.0)

        logger.info(f"Update downloaded: {dest_path} ({downloaded} bytes)")
        return dest_path

    except Exception as e:
        logger.error(f"Download failed: {e}")
        # Cleanup partial download
        if os.path.exists(dest_path):
            try:
                os.remove(dest_path)
            except OSError:
                pass
        return None


def install_update(installer_path: str) -> bool:
    """
    Launch the installer in silent mode and exit the current app.
    The installer will:
    1. Close the running app (via CloseApplications)
    2. Install the new version over the old one
    3. Relaunch the app after install
    Returns True if installer was launched successfully.
    """
    if not os.path.exists(installer_path):
        logger.error(f"Installer not found: {installer_path}")
        return False

    try:
        # Launch installer with /SILENT flag (no user interaction, shows progress)
        # /CLOSEAPPLICATIONS will close CheckPilot.exe before installing
        # /RESTARTAPPLICATIONS will relaunch after install
        cmd = [
            installer_path,
            "/SILENT",
            "/CLOSEAPPLICATIONS",
            "/RESTARTAPPLICATIONS",
            "/NOCANCEL",
        ]

        logger.info(f"Launching installer: {' '.join(cmd)}")

        # Use subprocess.Popen so we don't wait for it
        subprocess.Popen(
            cmd,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )

        return True

    except Exception as e:
        logger.error(f"Failed to launch installer: {e}")
        return False


def download_and_install(
    url: str,
    progress_callback: Optional[Callable[[float, str], None]] = None,
    done_callback: Optional[Callable[[bool, str], None]] = None,
):
    """
    Background thread: download update then prompt to install.
    progress_callback(progress_float, status_text)
    done_callback(success, installer_path_or_error)
    """
    def _worker():
        try:
            if progress_callback:
                progress_callback(0.0, "Đang tải bản cập nhật...")

            def _on_progress(p):
                if progress_callback:
                    progress_callback(p, f"Đang tải... {int(p * 100)}%")

            path = download_update(url, progress_callback=_on_progress)

            if path:
                if progress_callback:
                    progress_callback(1.0, "Tải xong! Sẵn sàng cài đặt.")
                if done_callback:
                    done_callback(True, path)
            else:
                if done_callback:
                    done_callback(False, "Tải bản cập nhật thất bại.")

        except Exception as e:
            logger.error(f"Update worker error: {e}")
            if done_callback:
                done_callback(False, str(e))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread


def cleanup_old_updates():
    """Remove old downloaded installers to save disk space."""
    if not os.path.exists(UPDATE_DOWNLOAD_DIR):
        return
    try:
        for f in os.listdir(UPDATE_DOWNLOAD_DIR):
            fp = os.path.join(UPDATE_DOWNLOAD_DIR, f)
            if os.path.isfile(fp):
                # Remove files older than 7 days
                age = datetime.now().timestamp() - os.path.getmtime(fp)
                if age > 7 * 86400:
                    os.remove(fp)
    except Exception as e:
        logger.debug(f"Cleanup error: {e}")


# ── Internal helpers ──

def _version_newer(remote: str, local: str) -> bool:
    """Compare version strings like '2.3.0' > '2.2.0'."""
    try:
        r_parts = [int(x) for x in remote.split(".")]
        l_parts = [int(x) for x in local.split(".")]
        return r_parts > l_parts
    except:
        return False


def _checked_recently() -> bool:
    """Return True if checked within last 24 hours AND same version."""
    if not os.path.exists(UPDATE_CHECK_FILE):
        return False
    try:
        with open(UPDATE_CHECK_FILE, "r") as f:
            data = json.load(f)
        # If version changed (new install), force re-check
        if data.get("version") != CURRENT_VERSION:
            return False
        last = datetime.fromisoformat(data.get("last_check", "2000-01-01"))
        return (datetime.now() - last) < timedelta(hours=24)
    except:
        return False


def _save_check_time():
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(UPDATE_CHECK_FILE, "w") as f:
        json.dump({"last_check": datetime.now().isoformat(), "version": CURRENT_VERSION}, f)
