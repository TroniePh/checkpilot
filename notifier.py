"""Telegram notification module for CheckPilot."""
import html
import json
import logging
import os
import re
from datetime import datetime
from typing import Optional

import requests

from config import DATA_DIR


logger = logging.getLogger(__name__)
TELEGRAM_CONFIG_FILE = os.path.join(DATA_DIR, "telegram.json")


def _split_chat_ids(value) -> list:
    if isinstance(value, list):
        raw_values = value
    else:
        raw_values = re.split(r"[\n,;]+", str(value or ""))
    return [str(v).strip() for v in raw_values if str(v).strip()]


def _normalize_config(config: dict) -> dict:
    enabled = bool(config.get("enabled", False))
    recipients = []

    for item in config.get("recipients", []) or []:
        bot_token = str(item.get("bot_token", "")).strip()
        chat_id = str(item.get("chat_id", "")).strip()
        name = str(item.get("name", "")).strip()
        if bot_token and chat_id:
            recipients.append({"name": name, "bot_token": bot_token, "chat_id": chat_id})

    # Backward compatible old schema: one bot token + one or many chat ids.
    bot_token = str(config.get("bot_token", "")).strip()
    if bot_token:
        for chat_id in _split_chat_ids(config.get("chat_ids", config.get("chat_id", ""))):
            if not any(r["bot_token"] == bot_token and r["chat_id"] == chat_id for r in recipients):
                recipients.append({"name": "", "bot_token": bot_token, "chat_id": chat_id})

    first = recipients[0] if recipients else {"bot_token": "", "chat_id": ""}
    return {
        "enabled": enabled,
        "bot_token": bot_token or first.get("bot_token", ""),
        "chat_id": first.get("chat_id", ""),
        "chat_ids": [r["chat_id"] for r in recipients],
        "recipients": recipients,
    }


def load_telegram_config() -> dict:
    if os.path.exists(TELEGRAM_CONFIG_FILE):
        try:
            with open(TELEGRAM_CONFIG_FILE, "r", encoding="utf-8") as f:
                return _normalize_config(json.load(f))
        except Exception:
            logger.exception("Failed to load Telegram config")
    return _normalize_config({"enabled": False})


def save_telegram_config(config: dict):
    os.makedirs(DATA_DIR, exist_ok=True)
    normalized = _normalize_config(config)
    with open(TELEGRAM_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(normalized, f, indent=2, ensure_ascii=False)


def _recipients() -> list:
    cfg = load_telegram_config()
    if not cfg.get("enabled"):
        return []
    return cfg.get("recipients", [])


def send_message(text: str) -> bool:
    """Send text message to all configured Telegram recipients."""
    recipients = _recipients()
    if not recipients:
        return False
    ok_count = 0
    for recipient in recipients:
        try:
            url = f"https://api.telegram.org/bot{recipient['bot_token']}/sendMessage"
            resp = requests.post(url, json={
                "chat_id": recipient["chat_id"],
                "text": text,
                "parse_mode": "HTML",
            }, timeout=10)
            if resp.status_code == 200:
                ok_count += 1
            else:
                logger.warning("Telegram send failed for chat %s: HTTP %s", recipient["chat_id"], resp.status_code)
        except Exception as e:
            logger.warning("Telegram send failed for chat %s: %s", recipient.get("chat_id"), e)
    return ok_count > 0


def send_photo(photo_path: str, caption: str = "") -> bool:
    """Send screenshot to all configured Telegram recipients."""
    recipients = _recipients()
    if not recipients or not os.path.exists(photo_path):
        return False
    ok_count = 0
    for recipient in recipients:
        try:
            url = f"https://api.telegram.org/bot{recipient['bot_token']}/sendPhoto"
            with open(photo_path, "rb") as f:
                resp = requests.post(url, data={
                    "chat_id": recipient["chat_id"],
                    "caption": caption[:1024],
                }, files={"photo": f}, timeout=30)
            if resp.status_code == 200:
                ok_count += 1
            else:
                logger.warning("Telegram photo failed for chat %s: HTTP %s", recipient["chat_id"], resp.status_code)
        except Exception as e:
            logger.warning("Telegram photo failed for chat %s: %s", recipient.get("chat_id"), e)
    return ok_count > 0


def send_error_alert(error_msg: str, screenshot_path: Optional[str] = None,
                     template: str = "", site: str = "", question: str = "",
                     url: str = "", details=None):
    """Send formatted error alert with optional screenshot."""
    safe_error = html.escape(str(error_msg))
    text = (
        "<b>CheckPilot - Lỗi Automation</b>\n\n"
        f"<b>Lỗi:</b> {safe_error}\n"
    )
    if template:
        text += f"<b>Template:</b> {html.escape(template)}\n"
    if site:
        text += f"<b>Site:</b> {html.escape(site)}\n"
    if question:
        text += f"<b>Câu hỏi:</b> {html.escape(str(question)[:180])}\n"
    if url:
        text += f"<b>URL:</b> {html.escape(str(url)[:220])}\n"
    if details:
        if isinstance(details, (list, tuple)):
            detail_text = "\n".join(f"- {html.escape(str(d)[:180])}" for d in details[:6])
        else:
            detail_text = html.escape(str(details)[:800])
        text += f"\n<b>Chi tiết:</b>\n{detail_text}\n"
    text += f"<b>Thời gian:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"

    send_message(text)
    if screenshot_path and os.path.exists(screenshot_path):
        send_photo(screenshot_path, f"Screenshot loi: {template or ''} {str(error_msg)[:160]}".strip())


def send_success_report(template: str, site: str, items: int, errors: int,
                        screenshot_path: Optional[str] = None,
                        verified: bool = False, scheduled_time: str = "",
                        url: str = ""):
    """Send success notification with optional verified screenshot."""
    text = (
        "<b>CheckPilot - Inspection Done</b>\n\n"
        f"<b>Template:</b> {html.escape(template)}\n"
        f"<b>Site:</b> {html.escape(site)}\n"
        f"<b>Items:</b> {items}\n"
        f"<b>Errors:</b> {errors}\n"
        f"<b>Verified:</b> {'Yes' if verified else 'Not checked'}\n"
    )
    if scheduled_time:
        text += f"<b>Schedule:</b> {html.escape(scheduled_time)}\n"
    if url:
        text += f"<b>URL:</b> {html.escape(str(url)[:220])}\n"
    text += f"<b>Time:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    send_message(text)
    if screenshot_path and os.path.exists(screenshot_path):
        caption = (
            f"Saved OK: {template}\n"
            f"Site: {site}\n"
            f"Verified: {'Yes' if verified else 'Not checked'}\n"
            f"Time: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
        )
        send_photo(screenshot_path, caption)


def test_connection() -> tuple:
    """Test all configured Telegram recipients. Returns (success, message)."""
    cfg = load_telegram_config()
    recipients = cfg.get("recipients", [])
    if not recipients:
        return False, "Chưa cấu hình Bot Token hoặc Chat ID"
    ok_count = 0
    failures = []
    for recipient in recipients:
        try:
            url = f"https://api.telegram.org/bot{recipient['bot_token']}/getMe"
            resp = requests.get(url, timeout=10)
            if resp.status_code != 200:
                failures.append(f"{recipient['chat_id']}: Bot Token lỗi HTTP {resp.status_code}")
                continue
            bot_name = resp.json().get("result", {}).get("username", "Unknown")
            if _send_test_message(recipient, bot_name):
                ok_count += 1
            else:
                failures.append(f"{recipient['chat_id']}: không gửi được tin nhắn")
        except Exception as e:
            failures.append(f"{recipient.get('chat_id', '?')}: {e}")

    if ok_count == len(recipients):
        return True, f"OK - đã gửi test tới {ok_count} chat"
    if ok_count > 0:
        return True, f"OK một phần: {ok_count}/{len(recipients)} chat. Lỗi: {'; '.join(failures[:2])}"
    return False, "Không gửi được Telegram: " + "; ".join(failures[:3])


def _send_test_message(recipient: dict, bot_name: str) -> bool:
    try:
        url = f"https://api.telegram.org/bot{recipient['bot_token']}/sendMessage"
        resp = requests.post(url, json={
            "chat_id": recipient["chat_id"],
            "text": f"CheckPilot test - Kết nối thành công qua @{bot_name}",
        }, timeout=10)
        return resp.status_code == 200
    except Exception:
        return False


def send_daily_summary(total: int, success: int, failed: int, skipped: int = 0):
    """Send end-of-run summary via Telegram."""
    text = (
        "<b>CheckPilot - Daily Summary</b>\n\n"
        f"<b>Total:</b> {total}\n"
        f"<b>Success:</b> {success}\n"
        f"<b>Failed:</b> {failed}\n"
    )
    if skipped:
        text += f"<b>Skipped (already done):</b> {skipped}\n"
    text += f"\n<b>Time:</b> {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}"
    send_message(text)
