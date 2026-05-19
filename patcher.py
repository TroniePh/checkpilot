"""
Patch system for CheckPilot.
Downloads and replaces individual .py files without requiring full installer.
Supports hot-patching for bug fixes and small updates.

How it works:
1. version.json on server has a "patches" array
2. Each patch has: file name, download URL, hash for verification
3. App downloads changed files → replaces in install dir → restarts

This avoids re-downloading the full 200MB+ installer for small fixes.
"""
import os
import sys
import json
import hashlib
import logging
import shutil
import threading
import subprocess
import requests
from typing import List, Dict, Optional, Callable
from config import DATA_DIR, INSTALL_DIR

logger = logging.getLogger(__name__)

PATCH_DOWNLOAD_DIR = os.path.join(DATA_DIR, "patches")
PATCH_BACKUP_DIR = os.path.join(DATA_DIR, "patch_backups")


def check_for_patches(version_data: dict) -> List[Dict]:
    """
    Check if there are patches available in version.json.
    Returns list of patch entries that need to be applied.
    
    version.json format:
    {
        "version": "2.3.1",
        "update_type": "patch",   // "patch" or "full"
        "patches": [
            {
                "file": "watchdog.py",
                "url": "https://raw.githubusercontent.com/TroniePh/checkpilot/main/patches/2.3.1/watchdog.py",
                "hash": "sha256:abc123...",
                "target": "_internal/watchdog.py"  // relative path in install dir (optional)
            }
        ],
        ...
    }
    """
    patches = version_data.get("patches", [])
    if not patches:
        return []

    update_type = version_data.get("update_type", "full")
    if update_type != "patch":
        return []

    return patches


def download_patches(
    patches: List[Dict],
    progress_callback: Optional[Callable[[float, str], None]] = None,
) -> List[Dict]:
    """
    Download all patch files.
    Returns list of successfully downloaded patches with local paths.
    """
    os.makedirs(PATCH_DOWNLOAD_DIR, exist_ok=True)
    downloaded = []
    total = len(patches)

    for idx, patch in enumerate(patches):
        filename = patch.get("file", "")
        url = patch.get("url", "")
        expected_hash = patch.get("hash", "")

        if not filename or not url:
            logger.warning(f"Patch entry missing file/url: {patch}")
            continue

        if progress_callback:
            progress_callback((idx / total), f"Đang tải {filename}...")

        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()

            # Save to temp location
            local_path = os.path.join(PATCH_DOWNLOAD_DIR, filename)
            with open(local_path, "wb") as f:
                f.write(resp.content)

            # Verify hash if provided
            if expected_hash:
                actual_hash = _file_hash(local_path)
                if expected_hash.startswith("sha256:"):
                    expected = expected_hash[7:]
                else:
                    expected = expected_hash

                if actual_hash != expected:
                    logger.error(f"Hash mismatch for {filename}: expected {expected[:16]}..., got {actual_hash[:16]}...")
                    os.remove(local_path)
                    continue

            patch_info = dict(patch)
            patch_info["local_path"] = local_path
            downloaded.append(patch_info)
            logger.info(f"Patch downloaded: {filename}")

        except Exception as e:
            logger.error(f"Failed to download patch {filename}: {e}")
            continue

    if progress_callback:
        progress_callback(1.0, f"Tải xong {len(downloaded)}/{total} file")

    return downloaded


def apply_patches(patches: List[Dict]) -> tuple:
    """
    Apply downloaded patches by replacing files in the install directory.
    Creates backups before replacing.
    Returns (success_count, error_list)
    """
    os.makedirs(PATCH_BACKUP_DIR, exist_ok=True)
    success = 0
    errors = []

    for patch in patches:
        filename = patch.get("file", "")
        local_path = patch.get("local_path", "")
        # Target path: either specified or default to _internal/ for frozen apps
        target_rel = patch.get("target", "")

        if not local_path or not os.path.exists(local_path):
            errors.append(f"{filename}: file not downloaded")
            continue

        # Determine destination
        if target_rel:
            dest = os.path.join(INSTALL_DIR, target_rel)
        elif getattr(sys, "frozen", False):
            # PyInstaller frozen app: .py files are in _internal/
            dest = os.path.join(INSTALL_DIR, "_internal", filename)
        else:
            # Dev mode: same directory
            dest = os.path.join(INSTALL_DIR, filename)

        try:
            # Backup existing file
            if os.path.exists(dest):
                backup_name = f"{filename}.bak.{_timestamp()}"
                backup_path = os.path.join(PATCH_BACKUP_DIR, backup_name)
                shutil.copy2(dest, backup_path)
                logger.info(f"Backup: {dest} -> {backup_path}")

            # Copy new file
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(local_path, dest)
            logger.info(f"Patched: {filename} -> {dest}")
            success += 1

        except PermissionError:
            errors.append(f"{filename}: Permission denied (app đang chạy?)")
        except Exception as e:
            errors.append(f"{filename}: {str(e)}")

    # Cleanup downloaded patches
    try:
        for patch in patches:
            lp = patch.get("local_path", "")
            if lp and os.path.exists(lp):
                os.remove(lp)
    except:
        pass

    return success, errors


def apply_patches_and_restart(
    patches: List[Dict],
    progress_callback: Optional[Callable[[float, str], None]] = None,
    done_callback: Optional[Callable[[bool, str], None]] = None,
):
    """
    Background thread: download patches, apply, and restart app.
    """
    def _worker():
        try:
            # Download
            downloaded = download_patches(patches, progress_callback)

            if not downloaded:
                if done_callback:
                    done_callback(False, "Không tải được patch nào.")
                return

            # Apply
            if progress_callback:
                progress_callback(0.9, "Đang áp dụng bản vá...")

            success, errors = apply_patches(downloaded)

            if errors:
                msg = f"Đã vá {success} file. Lỗi: {'; '.join(errors)}"
                if done_callback:
                    done_callback(success > 0, msg)
            else:
                if done_callback:
                    done_callback(True, f"Đã vá {success} file thành công.")

        except Exception as e:
            logger.error(f"Patch worker error: {e}")
            if done_callback:
                done_callback(False, str(e))

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return thread


def restart_app():
    """Restart the application after patching."""
    try:
        if getattr(sys, "frozen", False):
            # Frozen exe: restart the exe
            exe = sys.executable
            subprocess.Popen([exe], cwd=INSTALL_DIR)
        else:
            # Dev mode: restart python script
            python = sys.executable
            script = os.path.join(INSTALL_DIR, "main.py")
            subprocess.Popen([python, script], cwd=INSTALL_DIR)
    except Exception as e:
        logger.error(f"Restart failed: {e}")


def rollback_patches():
    """Rollback last applied patches from backup."""
    if not os.path.exists(PATCH_BACKUP_DIR):
        return False, "Không có backup"

    backups = sorted(os.listdir(PATCH_BACKUP_DIR), reverse=True)
    if not backups:
        return False, "Không có backup"

    restored = 0
    for bak_file in backups:
        # Format: filename.py.bak.20240101_120000
        parts = bak_file.split(".bak.")
        if len(parts) != 2:
            continue
        original_name = parts[0]

        bak_path = os.path.join(PATCH_BACKUP_DIR, bak_file)

        if getattr(sys, "frozen", False):
            dest = os.path.join(INSTALL_DIR, "_internal", original_name)
        else:
            dest = os.path.join(INSTALL_DIR, original_name)

        try:
            shutil.copy2(bak_path, dest)
            os.remove(bak_path)
            restored += 1
        except:
            pass

    return restored > 0, f"Đã khôi phục {restored} file"


# ── Helpers ──

def _file_hash(path: str) -> str:
    """Calculate SHA256 hash of a file."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _timestamp() -> str:
    from datetime import datetime
    return datetime.now().strftime("%Y%m%d_%H%M%S")
