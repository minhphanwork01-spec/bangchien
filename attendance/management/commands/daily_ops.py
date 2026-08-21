"""
Lệnh gộp việc hàng ngày. Trên tài khoản PythonAnywhere free MỚI (sau 2026-01-15)
không còn scheduled task, nên lệnh này KHÔNG tự chạy — bộ kích hoạt thật là
GitHub Actions gọi endpoint /internal/daily-ops/ (xem .github/workflows/daily-ops.yml).

Lệnh này giữ lại để: chạy tay khi cần, hoặc gắn vào scheduled task nếu lên paid.
Phần Discord chỉ gửi khi DISCORD_WEBHOOK_URL có trong .env (mặc định đã bỏ —
tin nhắc do GitHub Actions gửi từ IP không bị Discord chặn).
"""
import os

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from attendance import ops
from attendance.models import Attendance, WarEvent
from attendance.notify import send_discord


class Command(BaseCommand):
    help = "Việc hàng ngày: tạo event tuần, backup thứ 2 (Discord do GitHub Actions lo)."

    def handle(self, *args, **options):
        now = timezone.localtime()
        summary = ops.run_daily_ops(now)
        if summary["event_created"]:
            self.stdout.write(f"Tạo event: {summary['event']}")
        if summary["backup"]:
            self.stdout.write(f"Backup: {summary['backup']}")

        # Fallback Discord — chỉ chạy nếu còn khai URL trong .env
        days = {
            int(d)
            for d in os.getenv("DISCORD_NOTIFY_DAYS", "0,3").split(",")
            if d.strip().isdigit()
        }
        if now.weekday() not in days or not os.getenv("DISCORD_WEBHOOK_URL", "").strip():
            return
        site = os.getenv("SITE_URL", "").rstrip("/")
        link = f"{site}/checkin/" if site else "trang báo danh"
        current = WarEvent.objects.filter(
            event_type=WarEvent.EventType.WAR, is_current=True
        ).first()
        if not current:
            return
        mention = os.getenv("DISCORD_MENTION_EVERYONE", "true").strip().lower() in {
            "1", "true", "yes", "on",
        }
        if now.weekday() == min(days):
            msg = f"⚔️ **{current.title}** đã mở sổ báo danh — vào điểm danh tại {link}"
        else:
            joined = Attendance.objects.filter(
                war_event=current, status=Attendance.Status.JOINED
            ).count()
            total = getattr(settings, "WAR_SLOT_CAPACITY", 60)
            if current.deadline_at:
                d = timezone.localtime(current.deadline_at)
                vn_day = ["thứ 2", "thứ 3", "thứ 4", "thứ 5", "thứ 6", "thứ 7", "Chủ nhật"][d.weekday()]
                deadline = f"{d.strftime('%H:%M')} {vn_day}"
            else:
                deadline = "trước giờ đánh"
            msg = (
                f"⏳ Nhắc báo danh **{current.title}**: hiện **{joined}/{total}** đã điểm danh. "
                f"Chốt sổ {deadline} — {link}"
            )
        send_discord(msg, mention_everyone=mention)
