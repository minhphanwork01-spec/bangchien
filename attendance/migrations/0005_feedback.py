# Generated manually for BangCheck feedback feature

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0004_clear_attendance_note"),
    ]

    operations = [
        migrations.AddField(
            model_name="warevent",
            name="battle_start_at",
            field=models.DateTimeField("Giờ bắt đầu bang chiến", null=True, blank=True),
        ),
        migrations.CreateModel(
            name="BattleFeedback",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("content", models.TextField("Nội dung feedback")),
                ("device_id_hash", models.CharField("Device hash", max_length=64, blank=True, db_index=True)),
                ("member_id_hash", models.CharField("Member hash", max_length=64, blank=True)),
                ("ip_hash", models.CharField("IP hash", max_length=64, blank=True)),
                ("user_agent_hash", models.CharField("User-Agent hash", max_length=64, blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("war_event", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="feedbacks", to="attendance.warevent", verbose_name="Sự kiện bang chiến")),
            ],
            options={
                "verbose_name": "Feedback bang chiến",
                "verbose_name_plural": "Feedback bang chiến",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="battlefeedback",
            constraint=models.UniqueConstraint(fields=("war_event", "device_id_hash"), name="unique_feedback_per_device_event"),
        ),
        migrations.AddIndex(
            model_name="battlefeedback",
            index=models.Index(fields=["war_event", "created_at"], name="attendance_b_war_eve_7dd3a8_idx"),
        ),
    ]
