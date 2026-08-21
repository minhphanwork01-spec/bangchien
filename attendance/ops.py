"""
Logic vận hành định kỳ, tách riêng để gọi được từ HAI nơi:
- endpoint /internal/daily-ops/ (GitHub Actions gõ cửa hàng ngày — đường chính,
  vì tài khoản PythonAnywhere free mới không còn scheduled task)
- lệnh `manage.py daily_ops` (chạy tay, hoặc scheduled task nếu sau này lên paid)

Mọi hàm đều idempotent: chạy lại bao nhiêu lần cũng không tạo trùng, không hại gì.
"""
import logging
import os
import shutil
from datetime import datetime, time as dtime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

from .models import WarEvent

logger = logging.getLogger("bangcheck")

BACKUP_KEEP = 8


def _env_int(name, default):
    try:
        return int(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def ensure_weekly_event(now=None):
    """
    Tạo event bang chiến của thứ 7 sắp tới nếu chưa có (mặc định thứ 7 20:00,
    khóa sổ trước tối thiểu 2 tiếng; override qua .env WAR_WEEKDAY/WAR_TIME/
    WAR_DEADLINE_OFFSET_MIN). Trả về (event, created: bool).
    """
    now = now or timezone.localtime()
    weekday = _env_int("WAR_WEEKDAY", 5)  # 5 = thứ 7
    hh, mm = (os.getenv("WAR_TIME", "20:00").split(":") + ["0"])[:2]
    offset_min = max(120, _env_int("WAR_DEADLINE_OFFSET_MIN", 120))

    days_ahead = (weekday - now.weekday()) % 7
    target_date = now.date() + timedelta(days=days_ahead)
    battle_at = timezone.make_aware(
        datetime.combine(target_date, dtime(int(hh), int(mm))),
        timezone.get_current_timezone(),
    )
    if battle_at <= timezone.now():
        target_date += timedelta(days=7)
        battle_at += timedelta(days=7)

    event, created = WarEvent.objects.get_or_create(
        event_type=WarEvent.EventType.WAR,
        event_date=target_date,
        defaults={
            "title": f"Bang chiến {target_date.strftime('%d/%m')}",
            "battle_start_at": battle_at,
            "deadline_at": battle_at - timedelta(minutes=offset_min),
            "status": WarEvent.Status.OPEN,
        },
    )
    if created:
        logger.info("Đã tạo event %s.", event.title)

    # Chỉ tự set current khi không có event war current nào còn hợp lệ —
    # không đá văng event leader đang chủ động vận hành.
    current = WarEvent.objects.filter(
        event_type=WarEvent.EventType.WAR, is_current=True
    ).first()
    if current is None or current.event_date < now.date():
        event.is_current = True
        event.save()
        logger.info("Set current: %s", event.title)
    return event, created


def weekly_backup(now=None):
    """
    Backup SQLite mỗi thứ 2 (giờ VN), giữ BACKUP_KEEP bản mới nhất, tự dọn bản cũ.
    Trả về tên file backup vừa tạo, hoặc None nếu hôm nay không phải ngày backup
    / DB không phải SQLite.
    """
    now = now or timezone.localtime()
    if now.weekday() != 0:  # thứ 2
        return None
    db = settings.DATABASES["default"]
    if "sqlite" not in db["ENGINE"]:
        logger.info("DB không phải SQLite, bỏ qua backup file.")
        return None
    src = Path(db["NAME"])
    if not src.exists():
        return None
    backup_dir = Path(settings.BASE_DIR) / "backups"
    backup_dir.mkdir(exist_ok=True)
    dest = backup_dir / f"db-{now.strftime('%Y%m%d')}.sqlite3"
    shutil.copy2(src, dest)
    logger.info("Backup DB -> %s", dest.name)
    backups = sorted(backup_dir.glob("db-*.sqlite3"), reverse=True)
    for old in backups[BACKUP_KEEP:]:
        old.unlink()
        logger.info("Xoá backup cũ %s", old.name)
    return dest.name


def run_daily_ops(now=None):
    """Chạy trọn bộ việc hàng ngày, trả summary JSON-ready cho endpoint."""
    now = now or timezone.localtime()
    event, created = ensure_weekly_event(now)
    backup_name = weekly_backup(now)
    return {
        "ok": True,
        "event": event.title,
        "event_created": created,
        "backup": backup_name,
    }
