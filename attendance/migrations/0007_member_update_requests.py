from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("attendance", "0006_event_type_scrim"),
    ]

    operations = [
        migrations.AlterField(
            model_name="member",
            name="battle_team",
            field=models.CharField(
                blank=True,
                choices=[
                    ("", "Chưa xếp"),
                    ("defense", "Team thủ"),
                    ("offense", "Team công"),
                    ("mid", "Team mid"),
                    ("supply", "Team vật tư"),
                ],
                default="",
                max_length=20,
                verbose_name="Đội hình bang chiến",
            ),
        ),
        migrations.AlterModelOptions(
            name="memberrequest",
            options={
                "ordering": ["-created_at"],
                "verbose_name": "Yêu cầu thành viên",
                "verbose_name_plural": "Yêu cầu thành viên",
            },
        ),
        migrations.AddField(
            model_name="memberrequest",
            name="request_type",
            field=models.CharField(
                choices=[("add", "Tạo mới"), ("update", "Chỉnh thông tin")],
                default="add",
                max_length=20,
                verbose_name="Loại yêu cầu",
            ),
        ),
        migrations.AddField(
            model_name="memberrequest",
            name="target_member",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="change_requests",
                to="attendance.member",
                verbose_name="Nhân vật cần chỉnh",
            ),
        ),
        migrations.AddField(
            model_name="memberrequest",
            name="original_name",
            field=models.CharField(blank=True, max_length=100, verbose_name="Tên ban đầu"),
        ),
        migrations.AddField(
            model_name="memberrequest",
            name="original_class_name",
            field=models.CharField(blank=True, max_length=50, verbose_name="Phái ban đầu"),
        ),
        migrations.AddField(
            model_name="memberrequest",
            name="original_class_variant",
            field=models.CharField(blank=True, max_length=50, verbose_name="Hệ/phân nhánh ban đầu"),
        ),
        migrations.AddField(
            model_name="memberrequest",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="Xử lý lúc"),
        ),
        migrations.AddField(
            model_name="memberrequest",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_member_requests",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Người xử lý",
            ),
        ),
        migrations.AddField(
            model_name="memberrequest",
            name="review_note",
            field=models.TextField(blank=True, verbose_name="Ghi chú xử lý"),
        ),
        migrations.RenameIndex(
            model_name="attendance",
            old_name="attendance_war_event_bt_pos_idx",
            new_name="att_war_team_pos_idx",
        ),
        migrations.RenameIndex(
            model_name="battlefeedback",
            old_name="attendance_b_war_eve_7dd3a8_idx",
            new_name="att_feedback_event_time_idx",
        ),
        migrations.AddIndex(
            model_name="memberrequest",
            index=models.Index(
                fields=["request_type", "status"],
                name="att_mreq_type_status_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="memberrequest",
            index=models.Index(
                fields=["target_member", "status"],
                name="att_mreq_target_status_idx",
            ),
        ),
    ]
