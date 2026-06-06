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
import re
from typing import Optional, Tuple, Dict
from cryptography.fernet import Fernet

from config import DATA_DIR

SESSION_STATE_FILE = os.path.join(DATA_DIR, "sc_session.json")
CREDENTIALS_FILE = os.path.join(DATA_DIR, "sc_credentials.enc")
ACCOUNTS_FILE = os.path.join(DATA_DIR, "sc_accounts.enc")


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


def normalize_account_name(account_name: str = "") -> str:
    return str(account_name or "").strip()


def _safe_profile_slug(account_name: str) -> str:
    account_name = normalize_account_name(account_name)
    slug = re.sub(r"[^A-Za-z0-9_.-]+", "_", account_name).strip("._")[:64] or "profile"
    digest = hashlib.sha256(account_name.encode("utf-8")).hexdigest()[:10]
    return f"{slug}_{digest}"


def _session_file_for(account_name: str = "") -> str:
    account_name = normalize_account_name(account_name)
    if not account_name:
        return SESSION_STATE_FILE
    return os.path.join(DATA_DIR, f"sc_session_{_safe_profile_slug(account_name)}.json")


def _empty_account_store() -> dict:
    return {"profiles": {}}


def _load_account_store() -> dict:
    if not os.path.exists(ACCOUNTS_FILE):
        return _empty_account_store()
    try:
        cipher = _get_cipher()
        with open(ACCOUNTS_FILE, "rb") as f:
            encrypted = f.read()
        decrypted = cipher.decrypt(encrypted)
        data = json.loads(decrypted.decode())
        if isinstance(data, dict):
            data.setdefault("profiles", {})
            if isinstance(data["profiles"], dict):
                return data
    except Exception:
        pass
    return _empty_account_store()


def _save_account_store(data: dict) -> bool:
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        cipher = _get_cipher()
        payload = json.dumps(data, ensure_ascii=False).encode()
        encrypted = cipher.encrypt(payload)
        with open(ACCOUNTS_FILE, "wb") as f:
            f.write(encrypted)
        return True
    except Exception:
        return False


def list_account_profiles() -> Dict[str, dict]:
    """Return saved named SafetyCulture profiles without passwords."""
    profiles = _load_account_store().get("profiles", {})
    safe = {}
    for name, profile in profiles.items():
        if not isinstance(profile, dict):
            continue
        safe[name] = {
            "email": profile.get("email", ""),
            "template_folder_url": profile.get("template_folder_url", ""),
            "template_folder_name": profile.get("template_folder_name", ""),
        }
    return safe


def get_account_profile(account_name: str = "") -> dict:
    account_name = normalize_account_name(account_name)
    if not account_name:
        return {}
    profile = _load_account_store().get("profiles", {}).get(account_name, {})
    if not isinstance(profile, dict):
        return {}
    return {
        "email": profile.get("email", ""),
        "template_folder_url": profile.get("template_folder_url", ""),
        "template_folder_name": profile.get("template_folder_name", ""),
    }


def save_account_profile(
    account_name: str,
    email: str,
    password: str,
    template_folder_url: str = "",
    template_folder_name: str = "",
) -> bool:
    """Encrypt and save a named SafetyCulture account profile."""
    account_name = normalize_account_name(account_name)
    if not account_name or not email or not password:
        return False
    store = _load_account_store()
    store.setdefault("profiles", {})
    store["profiles"][account_name] = {
        "email": str(email).strip(),
        "password": str(password),
        "template_folder_url": str(template_folder_url or "").strip(),
        "template_folder_name": str(template_folder_name or "").strip(),
    }
    return _save_account_store(store)


def delete_account_profile(account_name: str) -> bool:
    account_name = normalize_account_name(account_name)
    if not account_name:
        return False
    store = _load_account_store()
    profiles = store.setdefault("profiles", {})
    removed = profiles.pop(account_name, None) is not None
    if removed:
        _save_account_store(store)
    clear_session(account_name)
    return removed


# ═══════════════════════════════════════════════════════════════════════════
# COOKIE / SESSION PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════

def has_saved_session(account_name: str = "") -> bool:
    """Check if we have a saved browser session."""
    return os.path.exists(_session_file_for(account_name))


def save_session_state(page, account_name: str = "") -> bool:
    """Save current browser state (cookies + localStorage) after login."""
    try:
        state = page.context.storage_state()
        with open(_session_file_for(account_name), "w", encoding="utf-8") as f:
            json.dump(state, f)
        return True
    except Exception:
        return False


def get_session_state_path(account_name: str = "") -> Optional[str]:
    """Get path to saved session state file (for context creation)."""
    path = _session_file_for(account_name)
    if os.path.exists(path):
        return path
    return None


def clear_session(account_name: str = ""):
    """Delete saved session."""
    path = _session_file_for(account_name)
    if os.path.exists(path):
        os.remove(path)


# ═══════════════════════════════════════════════════════════════════════════
# CREDENTIAL STORAGE (encrypted)
# ═══════════════════════════════════════════════════════════════════════════

def has_saved_credentials(account_name: str = "") -> bool:
    """Check if credentials are stored."""
    account_name = normalize_account_name(account_name)
    if account_name:
        profile = _load_account_store().get("profiles", {}).get(account_name, {})
        return bool(isinstance(profile, dict) and profile.get("email") and profile.get("password"))
    return os.path.exists(CREDENTIALS_FILE)


def save_credentials(email: str, password: str, account_name: str = "") -> bool:
    """Encrypt and save SafetyCulture credentials."""
    if normalize_account_name(account_name):
        return save_account_profile(account_name, email, password)
    try:
        cipher = _get_cipher()
        data = json.dumps({"email": email, "password": password}).encode()
        encrypted = cipher.encrypt(data)
        with open(CREDENTIALS_FILE, "wb") as f:
            f.write(encrypted)
        return True
    except Exception:
        return False


def load_credentials(account_name: str = "") -> Optional[Tuple[str, str]]:
    """Load and decrypt stored credentials. Returns (email, password) or None."""
    account_name = normalize_account_name(account_name)
    if account_name:
        profile = _load_account_store().get("profiles", {}).get(account_name, {})
        if isinstance(profile, dict) and profile.get("email") and profile.get("password"):
            return profile["email"], profile["password"]
        return None
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


def clear_credentials(account_name: str = ""):
    """Delete stored credentials."""
    account_name = normalize_account_name(account_name)
    if account_name:
        delete_account_profile(account_name)
        return
    if os.path.exists(CREDENTIALS_FILE):
        os.remove(CREDENTIALS_FILE)


def clear_all(account_name: str = ""):
    """Clear all saved login data."""
    clear_session(account_name)
    clear_credentials(account_name)
