# Generated manually for BangCheck: Nghịch Thủy Hàn classes + party board fields.

from django.db import migrations, models


CLASS_CHOICES = [
    ("Thiết Y", "Thiết Y"),
    ("Huyết Hà", "Huyết Hà"),
    ("Toái Mộng", "Toái Mộng"),
    ("Thần Tương", "Thần Tương"),
    ("Cửu Linh", "Cửu Linh"),
    ("Long Ngâm", "Long Ngâm"),
    ("Tố Vấn", "Tố Vấn"),
]

VARIANT_CHOICES = [
    ("Phá", "Phá"),
    ("Ngự", "Ngự"),
    ("Thiên Vấn", "Thiên Vấn"),
    ("Tố Tâm", "Tố Tâm"),
]

BATTLE_TEAM_CHOICES = [
    ("", "Chưa xếp"),
    ("defense", "Team thủ"),
    ("offense", "Team công"),
    ("mid", "Team mid"),
]

LEGACY_CLASS_MAP = {
    "Kiếm Sĩ": "Long Ngâm",
    "Pháp Sư": "Thần Tương",
    "Cung Thủ": "Thần Tương",
    "Đạo Sĩ": "Tố Vấn",
    "Thích Khách": "Toái Mộng",
    "Võ Tướng": "Thiết Y",
}


def migrate_legacy_classes(apps, schema_editor):
    Member = apps.get_model("attendance", "Member")
    MemberRequest = apps.get_model("attendance", "MemberRequest")

    for model in (Member, MemberRequest):
        for obj in model.objects.all():
            if obj.class_name in LEGACY_CLASS_MAP:
                obj.class_name = LEGACY_CLASS_MAP[obj.class_name]
                # Gợi ý variant mặc định cho dữ liệu demo cũ; dữ liệu thật có thể sửa lại trong Leader/Admin.
                if obj.class_name == "Thiết Y" and not getattr(obj, "class_variant", ""):
                    obj.class_variant = "Ngự"
                if obj.class_name == "Tố Vấn" and not getattr(obj, "class_variant", ""):
                    obj.class_variant = "Tố Tâm"
                obj.save()


class Migration(migrations.Migration):

    dependencies = [
        ("attendance", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="member",
            name="search_name",
            field=models.CharField(editable=False, max_length=220, verbose_name="Tên tìm kiếm (không dấu)"),
        ),
        migrations.AlterField(
            model_name="member",
            name="class_name",
            field=models.CharField(blank=True, choices=CLASS_CHOICES, max_length=50, verbose_name="Phái"),
        ),
        migrations.AddField(
            model_name="member",
            name="class_variant",
            field=models.CharField(blank=True, choices=VARIANT_CHOICES, max_length=50, verbose_name="Hệ/phân nhánh"),
        ),
        migrations.AddField(
            model_name="member",
            name="battle_team",
            field=models.CharField(blank=True, choices=BATTLE_TEAM_CHOICES, default="", max_length=20, verbose_name="Đội hình bang chiến"),
        ),
        migrations.AddField(
            model_name="member",
            name="battle_position",
            field=models.PositiveSmallIntegerField(blank=True, null=True, verbose_name="Vị trí đội hình"),
        ),
        migrations.AlterField(
            model_name="memberrequest",
            name="class_name",
            field=models.CharField(blank=True, choices=CLASS_CHOICES, max_length=50, verbose_name="Phái"),
        ),
        migrations.AddField(
            model_name="memberrequest",
            name="class_variant",
            field=models.CharField(blank=True, choices=VARIANT_CHOICES, max_length=50, verbose_name="Hệ/phân nhánh"),
        ),
        migrations.AddIndex(
            model_name="member",
            index=models.Index(fields=["class_name"], name="attendance__class__95a4d4_idx"),
        ),
        migrations.AddIndex(
            model_name="member",
            index=models.Index(fields=["battle_team", "battle_position"], name="attendance__battle_7ec61d_idx"),
        ),
        migrations.RunPython(migrate_legacy_classes, migrations.RunPython.noop),
    ]
