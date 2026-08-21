"""Export feedback audit CSV for server owner/dev.

Usage:
    python manage.py export_feedback_audit
    python manage.py export_feedback_audit --event 12
    python manage.py export_feedback_audit --output feedback_audit.csv
"""

import csv
from pathlib import Path

from django.core.management.base import BaseCommand

from attendance.models import BattleFeedback, WarEvent


class Command(BaseCommand):
    help = "Export feedback audit CSV with hash fields. Run from shell only; no UI button."

    def add_arguments(self, parser):
        parser.add_argument("--event", type=int, help="WarEvent ID to export")
        parser.add_argument(
            "--output",
            type=str,
            default="feedback_audit.csv",
            help="Output CSV path, default feedback_audit.csv",
        )

    def handle(self, *args, **options):
        qs = BattleFeedback.objects.select_related("war_event").order_by("-created_at")
        event_id = options.get("event")
        if event_id:
            if not WarEvent.objects.filter(id=event_id).exists():
                self.stderr.write(self.style.ERROR(f"WarEvent id={event_id} không tồn tại."))
                return
            qs = qs.filter(war_event_id=event_id)

        output_path = Path(options["output"]).resolve()
        with output_path.open("w", encoding="utf-8-sig", newline="") as f:
            writer = csv.writer(f)
            writer.writerow([
                "feedback_id",
                "event_id",
                "event_title",
                "event_date",
                "content",
                "created_at",
                "updated_at",
                "device_id_hash",
                "member_id_hash",
                "ip_hash",
                "user_agent_hash",
            ])
            for fb in qs:
                writer.writerow([
                    fb.id,
                    fb.war_event_id,
                    fb.war_event.title,
                    fb.war_event.event_date,
                    fb.content,
                    fb.created_at.strftime("%Y-%m-%d %H:%M:%S"),
                    fb.updated_at.strftime("%Y-%m-%d %H:%M:%S"),
                    fb.device_id_hash,
                    fb.member_id_hash,
                    fb.ip_hash,
                    fb.user_agent_hash,
                ])

        self.stdout.write(self.style.SUCCESS(f"Exported {qs.count()} feedback rows to {output_path}"))
