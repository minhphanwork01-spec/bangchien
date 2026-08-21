"""
Gửi thông báo Discord qua webhook.

Webhook = URL bí mật gắn với MỘT channel, chỉ có quyền ĐĂNG tin vào channel đó
(không đọc, không thấy member, không liên quan account cá nhân nào).
URL để trong .env (DISCORD_WEBHOOK_URL), không hardcode, không commit.
"""
import logging
import os

import requests

logger = logging.getLogger("bangcheck")


def send_discord(message: str) -> bool:
    """POST một tin nhắn vào webhook. Không có URL -> bỏ qua êm (trả False)."""
    url = os.getenv("DISCORD_WEBHOOK_URL", "").strip()
    if not url:
        logger.info("DISCORD_WEBHOOK_URL chưa set, bỏ qua thông báo Discord.")
        return False
    try:
        resp = requests.post(url, json={"content": message}, timeout=10)
        resp.raise_for_status()
        logger.info("Đã gửi thông báo Discord (%s ký tự).", len(message))
        return True
    except requests.RequestException as exc:
        logger.warning("Gửi Discord thất bại: %s", exc)
        return False
