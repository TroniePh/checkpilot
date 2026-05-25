"""Authentication and license management for CheckPilot."""
import os
import json
import hashlib
import secrets
import time
from datetime import datetime, timedelta
from typing import Optional, Tuple

from config import BASE_DIR, DATA_DIR

# User database file (simple JSON-based for standalone app)
USER_DB_PATH = os.path.join(DATA_DIR, "users.db.json")
LICENSE_DB_PATH = os.path.join(DATA_DIR, "licenses.db.json")
SESSION_FILE = os.path.join(DATA_DIR, ".session")

os.makedirs(DATA_DIR, exist_ok=True)


def _hash_password(password: str, salt: str = None) -> Tuple[str, str]:
    """Hash password with salt using SHA-256."""
    if salt is None:
        salt = secrets.token_hex(16)
    hashed = hashlib.sha256((salt + password).encode()).hexdigest()
    return hashed, salt


def _load_db(path: str) -> dict:
    """Load JSON database."""
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_db(path: str, data: dict):
    """Save JSON database."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def init_default_admin():
    """Create default admin account if no users exist."""
    db = _load_db(USER_DB_PATH)
    if not db:
        hashed, salt = _hash_password("admin123")
        db["admin"] = {
            "password_hash": hashed,
            "salt": salt,
            "role": "admin",
            "full_name": "Administrator",
            "email": "admin@company.com",
            "created_at": datetime.now().isoformat(),
            "active": True,
            "must_change_password": True,
            "default_password": True,
        }
        _save_db(USER_DB_PATH, db)
    else:
        admin = db.get("admin")
        if admin and admin.get("active", True):
            default_hash, _ = _hash_password("admin123", admin["salt"])
            if admin.get("password_hash") == default_hash:
                admin["must_change_password"] = True
                admin["default_password"] = True
                _save_db(USER_DB_PATH, db)

    # Init license db
    lic_db = _load_db(LICENSE_DB_PATH)
    if not lic_db:
        lic_db["default"] = {
            "key": "CHECKPILOT-TRIAL-2026",
            "plan": "trial",
            "max_inspections": 50,
            "expires_at": (datetime.now() + timedelta(days=30)).isoformat(),
            "created_at": datetime.now().isoformat(),
        }
        _save_db(LICENSE_DB_PATH, lic_db)


def authenticate(username: str, password: str) -> Tuple[bool, str, dict]:
    """
    Authenticate user.
    Returns: (success, message, user_data)
    """
    db = _load_db(USER_DB_PATH)

    if username not in db:
        return False, "Tài khoản không tồn tại.", {}

    user = db[username]

    if not user.get("active", True):
        return False, "Tài khoản đã bị vô hiệu hóa.", {}

    hashed, _ = _hash_password(password, user["salt"])
    if hashed != user["password_hash"]:
        return False, "Mật khẩu không đúng.", {}

    # Save session
    session = {
        "username": username,
        "login_time": datetime.now().isoformat(),
        "token": secrets.token_hex(32),
    }
    _save_db(SESSION_FILE, session)

    return True, "Đăng nhập thành công!", user


def register_user(username: str, password: str, full_name: str, email: str,
                  role: str = "user", admin_username: str = None) -> Tuple[bool, str]:
    """Register a new user (admin only)."""
    db = _load_db(USER_DB_PATH)

    # Check admin permission
    if admin_username:
        admin = db.get(admin_username, {})
        if admin.get("role") != "admin":
            return False, "Chỉ admin mới có thể tạo tài khoản mới."

    if username in db:
        return False, "Username đã tồn tại."

    if len(password) < 6:
        return False, "Mật khẩu phải ít nhất 6 ký tự."

    hashed, salt = _hash_password(password)
    db[username] = {
        "password_hash": hashed,
        "salt": salt,
        "role": role,
        "full_name": full_name,
        "email": email,
        "created_at": datetime.now().isoformat(),
        "active": True,
    }
    _save_db(USER_DB_PATH, db)
    return True, "Tạo tài khoản thành công!"


def change_password(username: str, old_password: str, new_password: str) -> Tuple[bool, str]:
    """Change user password."""
    db = _load_db(USER_DB_PATH)

    if username not in db:
        return False, "Tài khoản không tồn tại."

    user = db[username]
    hashed, _ = _hash_password(old_password, user["salt"])
    if hashed != user["password_hash"]:
        return False, "Mật khẩu cũ không đúng."

    if len(new_password) < 6:
        return False, "Mật khẩu mới phải ít nhất 6 ký tự."

    new_hashed, new_salt = _hash_password(new_password)
    db[username]["password_hash"] = new_hashed
    db[username]["salt"] = new_salt
    db[username]["must_change_password"] = False
    db[username]["default_password"] = False
    _save_db(USER_DB_PATH, db)
    return True, "Đổi mật khẩu thành công!"


def get_license_info() -> dict:
    """Get current license information."""
    lic_db = _load_db(LICENSE_DB_PATH)
    if not lic_db:
        return {"plan": "expired", "valid": False, "days_remaining": 0}

    # Prioritize "active" license (activated by user), fallback to "default"
    if "active" in lic_db:
        lic = lic_db["active"]
    else:
        key = list(lic_db.keys())[0]
        lic = lic_db[key]

    expires = datetime.fromisoformat(lic["expires_at"])
    lic["valid"] = expires > datetime.now()
    lic["days_remaining"] = max(0, (expires - datetime.now()).days)

    return lic


def activate_license(license_key: str) -> Tuple[bool, str]:
    """Activate a license key."""
    # Valid license keys
    VALID_KEYS = {
        "SCAUTO-PREMIUM-3M-2024-DUYPH": {
            "plan": "premium",
            "max_inspections": 9999,
            "days": 90,
            "label": "Premium 3 tháng",
        },
        "SCAUTO-LIFETIME-FOREVER-DUYPH": {
            "plan": "lifetime",
            "max_inspections": 99999,
            "days": 36500,  # 100 years
            "label": "Lifetime (Vĩnh viễn)",
        },
    }

    if not license_key or len(license_key) < 5:
        return False, "License key không hợp lệ."

    key_upper = license_key.strip().upper()

    if key_upper not in VALID_KEYS:
        return False, "License key không đúng. Vui lòng liên hệ 0868609901."

    key_info = VALID_KEYS[key_upper]

    lic_db = _load_db(LICENSE_DB_PATH)
    lic_db["active"] = {
        "key": key_upper,
        "plan": key_info["plan"],
        "max_inspections": key_info["max_inspections"],
        "expires_at": (datetime.now() + timedelta(days=key_info["days"])).isoformat(),
        "created_at": datetime.now().isoformat(),
    }
    _save_db(LICENSE_DB_PATH, lic_db)
    return True, f"Kích hoạt thành công: {key_info['label']}"


def get_saved_session() -> Optional[dict]:
    """Check for existing session."""
    if not os.path.exists(SESSION_FILE):
        return None

    session = _load_db(SESSION_FILE)
    if not session:
        return None

    # Check session age (auto-expire after 7 days)
    login_time = datetime.fromisoformat(session.get("login_time", "2000-01-01"))
    if datetime.now() - login_time > timedelta(days=7):
        os.remove(SESSION_FILE)
        return None

    return session


def logout():
    """Clear session."""
    if os.path.exists(SESSION_FILE):
        os.remove(SESSION_FILE)


def get_all_users() -> dict:
    """Get all users (for admin panel)."""
    db = _load_db(USER_DB_PATH)
    # Remove sensitive fields
    safe_db = {}
    for username, data in db.items():
        safe_db[username] = {
            "full_name": data.get("full_name", ""),
            "email": data.get("email", ""),
            "role": data.get("role", "user"),
            "created_at": data.get("created_at", ""),
            "active": data.get("active", True),
        }
    return safe_db
