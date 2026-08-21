"""
attendance/management/commands/seed_demo_data.py

Tạo demo data: 20 members mẫu + 1 current WarEvent.
Chạy: python manage.py seed_demo_data
"""

from django.core.management.base import BaseCommand
from django.utils import timezone
import datetime

from attendance.models import Member, WarEvent, Attendance


DEMO_MEMBERS = [
    # Demo theo 7 phái Nghịch Thủy Hàn. Tên có dấu/khoảng trắng để test search_name.
    {"display_name": "Minh AbC", "class_name": "Thần Tương", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Long Ngâm 01", "class_name": "Long Ngâm", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Thiết Y Ngự", "class_name": "Thiết Y", "class_variant": "Ngự", "role": "", "team": "", "note": ""},
    {"display_name": "Thiết Y Phá", "class_name": "Thiết Y", "class_variant": "Phá", "role": "", "team": "", "note": ""},
    {"display_name": "Tố Vấn Tố Tâm", "class_name": "Tố Vấn", "class_variant": "Tố Tâm", "role": "", "team": "", "note": ""},
    {"display_name": "Tố Vấn Thiên Vấn", "class_name": "Tố Vấn", "class_variant": "Thiên Vấn", "role": "", "team": "", "note": ""},
    {"display_name": "Huyết Hà Alpha", "class_name": "Huyết Hà", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Toái Mộng Beta", "class_name": "Toái Mộng", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Cửu Linh Gamma", "class_name": "Cửu Linh", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Thần Tương Delta", "class_name": "Thần Tương", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Long Ngâm Epsilon", "class_name": "Long Ngâm", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Huyết Hà 02", "class_name": "Huyết Hà", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Toái Mộng 03", "class_name": "Toái Mộng", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Cửu Linh 04", "class_name": "Cửu Linh", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Thần Tương 05", "class_name": "Thần Tương", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Tố Vấn 06", "class_name": "Tố Vấn", "class_variant": "Tố Tâm", "role": "", "team": "", "note": ""},
    {"display_name": "Thiết Y 07", "class_name": "Thiết Y", "class_variant": "Ngự", "role": "", "team": "", "note": ""},
    {"display_name": "Long Ngâm 08", "class_name": "Long Ngâm", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Huyết Hà 09", "class_name": "Huyết Hà", "class_variant": "", "role": "", "team": "", "note": ""},
    {"display_name": "Toái Mộng 10", "class_name": "Toái Mộng", "class_variant": "", "role": "", "team": "", "note": ""},
]



class Command(BaseCommand):
    help = "Seed demo data: 20 members + 1 current WarEvent + một số attendance mẫu"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Xóa tất cả data cũ trước khi seed",
        )

    def handle(self, *args, **options):
        if options["reset"]:
            self.stdout.write("🗑️  Xóa data cũ...")
            Attendance.objects.all().delete()
            WarEvent.objects.all().delete()
            Member.objects.all().delete()

        # ── Tạo Members ──────────────────────────────
        created_members = []
        skipped = 0

        for data in DEMO_MEMBERS:
            member, created = Member.objects.get_or_create(
                display_name=data["display_name"],
                defaults={
                    "class_name": data["class_name"],
                    "class_variant": data.get("class_variant", ""),
                    "role": data["role"],
                    "team": data["team"],
                    "note": data["note"],
                    "active": True,
                },
            )
            if created:
                created_members.append(member)
                self.stdout.write(f"  ✅ Member: {member.display_name}")
            else:
                skipped += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"\n👥 Members: {len(created_members)} tạo mới, {skipped} đã tồn tại."
            )
        )

        # ── Tạo WarEvent ─────────────────────────────
        # Tìm thứ 7 gần nhất (hoặc hôm nay nếu là thứ 7)
        today = timezone.localdate()
        days_until_saturday = (5 - today.weekday()) % 7
        if days_until_saturday == 0 and today.weekday() != 5:
            days_until_saturday = 7
        next_saturday = today + datetime.timedelta(days=days_until_saturday)

        event_title = f"Bang Chiến {next_saturday.strftime('%d/%m/%Y')}"

        event, event_created = WarEvent.objects.get_or_create(
            event_type=WarEvent.EventType.WAR,
            event_date=next_saturday,
            defaults={
                "title": event_title,
                "event_type": WarEvent.EventType.WAR,
                "status": WarEvent.Status.OPEN,
                "is_current": True,
                "deadline_at": timezone.make_aware(
                    datetime.datetime.combine(next_saturday, datetime.time(19, 0))
                ),
                "team_notes": {
                    "defense": "Giữ trụ, ưu tiên bảo kê Tố Vấn.",
                    "offense": "Đẩy mục tiêu theo call, tập trung phá trụ.",
                    "mid": "Giữ mid, phản ứng nhanh khi thủ/công cần hỗ trợ.",
                    "supply": "Theo dõi vật tư, gọi bổ sung khi thiếu.",
                },
            },
        )

        if event_created:
            self.stdout.write(self.style.SUCCESS(f"📅 WarEvent tạo mới: {event}"))
        else:
            # Đặt là current nếu chưa phải
            if not event.is_current or event.status != WarEvent.Status.OPEN or event.event_type != WarEvent.EventType.WAR:
                event.event_type = WarEvent.EventType.WAR
                event.is_current = True
                event.status = WarEvent.Status.OPEN
                event.save()
            self.stdout.write(f"📅 WarEvent đã tồn tại: {event}")

        # ── Tạo Scrim demo riêng ──────────────────────
        scrim_date = next_saturday - datetime.timedelta(days=2)
        scrim_title = f"Scrim {scrim_date.strftime('%d/%m/%Y')}"
        scrim_event, scrim_created = WarEvent.objects.get_or_create(
            event_type=WarEvent.EventType.SCRIM,
            event_date=scrim_date,
            defaults={
                "title": scrim_title,
                "status": WarEvent.Status.OPEN,
                "is_current": True,
                "deadline_at": timezone.make_aware(
                    datetime.datetime.combine(scrim_date, datetime.time(20, 0))
                ),
            },
        )
        if scrim_created:
            self.stdout.write(self.style.SUCCESS(f"🎯 Scrim tạo mới: {scrim_event}"))
        else:
            if not scrim_event.is_current or scrim_event.status != WarEvent.Status.OPEN:
                scrim_event.is_current = True
                scrim_event.status = WarEvent.Status.OPEN
                scrim_event.save()
            self.stdout.write(f"🎯 Scrim đã tồn tại: {scrim_event}")

        # ── Tạo một số Attendance mẫu ────────────────
        all_members = list(Member.objects.filter(active=True))

        demo_attendances = [
            (0, "joined"),
            (1, "joined"),
            (2, "joined"),
            (4, "joined"),
            (5, "joined"),
            (6, "joined"),
            (7, "joined"),
            (8, "joined"),
            (10, "joined"),
            (3, "absent"),
            (9, "absent"),
        ]

        att_created = 0
        for idx, status in demo_attendances:
            if idx < len(all_members):
                member = all_members[idx]
                _, att_new = Attendance.objects.get_or_create(
                    war_event=event,
                    member=member,
                    defaults={"status": status, "source": "system"},
                )
                if att_new:
                    att_created += 1

        self.stdout.write(self.style.SUCCESS(f"📋 Attendance: {att_created} mẫu tạo mới."))

        # ── Summary ──────────────────────────────────
        self.stdout.write("\n" + "=" * 50)
        self.stdout.write(self.style.SUCCESS("✅ Seed hoàn tất!"))
        self.stdout.write(f"   Members active: {Member.objects.filter(active=True).count()}")
        self.stdout.write(f"   Current event: {event.title}")
        self.stdout.write(f"   Attendance records: {Attendance.objects.filter(war_event=event).count()}")
        self.stdout.write("\nBước tiếp theo:")
        self.stdout.write("  python manage.py createsuperuser")
        self.stdout.write("  python manage.py runserver")
        self.stdout.write("  Mở: http://127.0.0.1:8000/checkin/")
        self.stdout.write("  Admin: http://127.0.0.1:8000/admin/")
