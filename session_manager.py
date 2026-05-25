"""
Session & credential manager for SafetyCulture auto-login.

Two modes:
1. Cookie persistence: Save browser state after first login, reuse on next run.
2. Stored credentials: Encrypt and store SC email/password, auto-fill login form.

Credentials are encrypted with a machine-specific key (not plain text).
"""
import os
import json
import base64
import hashlib
import platform
from typing import Optional, Tuple
from cryptography.fernet import Fernet

from config import DATA_DIR

SESSION_STATE_FILE = os.path.join(DATA_DIR, "sc_session.json")
CREDENTIALS_FILE = os.path.join(DATA_DIR, "sc_credentials.enc")


def _get_machine_key() -> bytes:
    """
    Generate encryption key from machine-specific info.
    Not military-grade but prevents casual file copying.
    """
    # Combine machine identifiers
    machine_id = (
        platform.node() +
        platform.machine() +
        os.environ.get("USERNAME", os.environ.get("USER", "default")) +
        "SafetyCultureAuto2024"
    )
    # Derive a Fernet-compatible key
    key_hash = hashlib.sha256(machine_id.encode()).digest()
    return base64.urlsafe_b64encode(key_hash)


def _get_cipher() -> Fernet:
    """Get Fernet cipher with machine key."""
    return Fernet(_get_machine_key())


# ═══════════════════════════════════════════════════════════════════════════
# COOKIE / SESSION PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════

def has_saved_session() -> bool:
    """Check if we have a saved browser session."""
    return os.path.exists(SESSION_STATE_FILE)


def save_session_state(page) -> bool:
    """Save current browser state (cookies + localStorage) after login."""
    try:
        state = page.context.storage_state()
        with open(SESSION_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f)
        return True
    except Exception:
        return False


def get_session_state_path() -> Optional[str]:
    """Get path to saved session state file (for context creation)."""
    if os.path.exists(SESSION_STATE_FILE):
        return SESSION_STATE_FILE
    return None


def clear_session():
    """Delete saved session."""
    if os.path.exists(SESSION_STATE_FILE):
        os.remove(SESSION_STATE_FILE)


# ═══════════════════════════════════════════════════════════════════════════
# CREDENTIAL STORAGE (encrypted)
# ═══════════════════════════════════════════════════════════════════════════

def has_saved_credentials() -> bool:
    """Check if credentials are stored."""
    return os.path.exists(CREDENTIALS_FILE)


def save_credentials(email: str, password: str) -> bool:
    """Encrypt and save SafetyCulture credentials."""
    try:
        cipher = _get_cipher()
        data = json.dumps({"email": email, "password": password}).encode()
        encrypted = cipher.encrypt(data)
        with open(CREDENTIALS_FILE, "wb") as f:
            f.write(encrypted)
        return True
    except Exception:
        return False


def load_credentials() -> Optional[Tuple[str, str]]:
    """Load and decrypt stored credentials. Returns (email, password) or None."""
    if not os.path.exists(CREDENTIALS_FILE):
        return None
    try:
        cipher = _get_cipher()
        with open(CREDENTIALS_FILE, "rb") as f:
            encrypted = f.read()
        decrypted = cipher.decrypt(encrypted)
        data = json.loads(decrypted.decode())
        return data["email"], data["password"]
    except Exception:
        # Decryption failed (wrong machine, corrupted file, etc.)
        return None


def clear_credentials():
    """Delete stored credentials."""
    if os.path.exists(CREDENTIALS_FILE):
        os.remove(CREDENTIALS_FILE)


def clear_all():
    """Clear all saved login data."""
    clear_session()
    clear_credentials()
