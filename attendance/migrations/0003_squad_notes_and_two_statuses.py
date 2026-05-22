# Generated manually for BangCheck

from django.db import migrations, models


def map_old_statuses(apps, schema_editor):
    Attendance = apps.get_model("attendance", "Attendance")
    # Old statuses removed from UI. Preserve operational meaning by treating them as joined.
    Attendance.objects.filter(status__in=["late", "uncertain"]).update(status="joined")


def copy_member_party_positions_to_current_event(apps, schema_editor):
    """
    Previous versions stored party board position on Member.
    New version stores it on Attendance so every event/week can have different squad layout.
    Copy old positions into the current event only, if matching attendance exists.
    """
    Member = apps.get_model("attendance", "Member")
    Attendance = apps.get_model("attendance", "Attendance")
    WarEvent = apps.get_model("attendance", "WarEvent")

    current_event = WarEvent.objects.filter(is_current=True).first()
    if not current_event:
        return

    for member in Member.objects.exclude(battle_team="").exclude(battle_position__isnull=True):
        Attendance.objects.filter(war_event=current_event, member=member, status="joined").update(
            battle_team=member.battle_team,
            battle_position=member.battle_position,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0002_party_board_and_nsh_classes"),
    ]

    operations = [
        migrations.AddField(
            model_name="warevent",
            name="team_notes",
            field=models.JSONField("Ghi chú chiến thuật theo team", blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="attendance",
            name="strategy_note",
            field=models.CharField("Ghi chú skill/chiến thuật cá nhân", blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="attendance",
            name="battle_team",
            field=models.CharField("Team xếp đội theo event", blank=True, choices=[("", "Chưa xếp"), ("defense", "Team thủ"), ("offense", "Team công"), ("mid", "Team mid"), ("supply", "Team vật tư")], default="", max_length=20),
        ),
        migrations.AddField(
            model_name="attendance",
            name="battle_position",
            field=models.PositiveSmallIntegerField("Vị trí xếp đội theo event", blank=True, null=True),
        ),
        migrations.RunPython(map_old_statuses, migrations.RunPython.noop),
        migrations.RunPython(copy_member_party_positions_to_current_event, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="attendance",
            name="status",
            field=models.CharField("Trạng thái", choices=[("joined", "Tham gia"), ("absent", "Không tham gia")], max_length=20),
        ),
        migrations.AddIndex(
            model_name="attendance",
            index=models.Index(fields=["war_event", "battle_team", "battle_position"], name="attendance_war_event_bt_pos_idx"),
        ),
    ]
