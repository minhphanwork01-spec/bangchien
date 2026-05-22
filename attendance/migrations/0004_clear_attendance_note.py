# Generated manually for BangCheck

from django.db import migrations


def clear_attendance_notes(apps, schema_editor):
    Attendance = apps.get_model("attendance", "Attendance")
    Attendance.objects.exclude(note="").update(note="")


class Migration(migrations.Migration):
    dependencies = [
        ("attendance", "0003_squad_notes_and_two_statuses"),
    ]

    operations = [
        migrations.RunPython(clear_attendance_notes, migrations.RunPython.noop),
    ]
