"""
attendance/models.py

Models cho hệ thống điểm danh bang chiến.
Thiết kế theo nguyên tắc: attendance luôn lưu bằng member_id, không lưu tên text.
"""

import unicodedata
from django.db import models


def normalize_search_name(text: str) -> str:
    """
    Chuẩn hóa tên để tìm kiếm: bỏ dấu tiếng Việt, lowercase, gộp khoảng trắng.

    Lưu ý: search_name chỉ phục vụ tìm kiếm. Identity thật vẫn là member_id,
    nên việc normalize không bao giờ được dùng để tự gộp 2 nhân vật.
    """
    text = (text or "").lower()
    # Xử lý riêng ký tự đ/Đ vì NFD không decompose được
    text = text.replace("đ", "d").replace("Đ", "d")
    # Decompose và loại bỏ dấu tổ hợp (combining marks)
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    # Gộp whitespace để tìm kiếm ổn hơn với tên có dấu cách/ký tự lạ
    text = " ".join(text.split())
    compact = "".join(c for c in text if c.isalnum())
    # Lưu cả bản có khoảng trắng và bản compact để search được Minh ABC ⇄ MinhABC
    return f"{text} {compact}".strip()


CLASS_COLORS = {
    "Thiết Y": "thiet-y",
    "Huyết Hà": "huyet-ha",
    "Toái Mộng": "toai-mong",
    "Thần Tương": "than-tuong",
    "Cửu Linh": "cuu-linh",
    "Long Ngâm": "long-ngam",
    "Tố Vấn": "to-van",
}

# Icon chỉ dùng để phân biệt hệ/phân nhánh đặc biệt, không dùng icon riêng cho từng phái.
# Phái được phân biệt bằng màu trong CSS.
VARIANT_ICONS = {
    "Ngự": "🛡️",
    "Phá": "👊",
    "Thiên Vấn": "🦋",
    "Tố Tâm": "🌸",
}

# Chỉ 2 phái này có hệ/phân nhánh trong app.
# Các phái khác sẽ tự clear class_variant khi save để tránh dữ liệu bẩn.
VALID_CLASS_VARIANTS = {
    "Thiết Y": {"Ngự", "Phá"},
    "Tố Vấn": {"Thiên Vấn", "Tố Tâm"},
}


class Member(models.Model):
    """
    Thành viên bang. Đây là nguồn sự thật duy nhất cho danh sách thành viên.
    - Không xóa cứng nếu đã có attendance → dùng active=False.
    - search_name được tự động tạo từ display_name để tìm kiếm không dấu.
    """

    class Role(models.TextChoices):
        TANK = "tank", "Tank"
        HEALER = "healer", "Healer"
        DPS = "dps", "DPS"
        SUPPORT = "support", "Support"
        FLEX = "flex", "Flex"

    class ClassName(models.TextChoices):
        THIET_Y = "Thiết Y", "Thiết Y"
        HUYET_HA = "Huyết Hà", "Huyết Hà"
        TOAI_MONG = "Toái Mộng", "Toái Mộng"
        THAN_TUONG = "Thần Tương", "Thần Tương"
        CUU_LINH = "Cửu Linh", "Cửu Linh"
        LONG_NGAM = "Long Ngâm", "Long Ngâm"
        TO_VAN = "Tố Vấn", "Tố Vấn"

    class ClassVariant(models.TextChoices):
        NGU = "Ngự", "Ngự"
        PHA = "Phá", "Phá"
        THIEN_VAN = "Thiên Vấn", "Thiên Vấn"
        TO_TAM = "Tố Tâm", "Tố Tâm"

    class BattleTeam(models.TextChoices):
        UNASSIGNED = "", "Chưa xếp"
        DEFENSE = "defense", "Team thủ"
        OFFENSE = "offense", "Team công"
        MID = "mid", "Team mid"
        SUPPLY = "supply", "Team vật tư"

    display_name = models.CharField("Tên hiển thị", max_length=100)
    # Auto-generated từ display_name, không edit trực tiếp
    search_name = models.CharField("Tên tìm kiếm (không dấu)", max_length=220, editable=False)
    class_name = models.CharField("Phái", max_length=50, choices=ClassName.choices, blank=True)
    class_variant = models.CharField("Hệ/phân nhánh", max_length=50, choices=ClassVariant.choices, blank=True)
    role = models.CharField("Role", max_length=20, choices=Role.choices, blank=True)
    team = models.CharField("Đội/Tổ thường dùng", max_length=50, blank=True)
    battle_team = models.CharField("Đội hình bang chiến", max_length=20, choices=BattleTeam.choices, blank=True, default="")
    battle_position = models.PositiveSmallIntegerField("Vị trí đội hình", null=True, blank=True)
    note = models.TextField("Ghi chú", blank=True)
    active = models.BooleanField("Đang hoạt động", default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Thành viên"
        verbose_name_plural = "Thành viên"
        indexes = [
            models.Index(fields=["display_name"]),
            models.Index(fields=["search_name"]),
            models.Index(fields=["active"]),
            models.Index(fields=["class_name"]),
            models.Index(fields=["battle_team", "battle_position"]),
        ]

    def save(self, *args, **kwargs):
        # Auto-generate search_name mỗi khi save
        self.search_name = normalize_search_name(self.display_name)

        # Chỉ Thiết Y và Tố Vấn mới có hệ/phân nhánh.
        # Phái khác thì tự clear để tránh dữ liệu bẩn.
        allowed_variants = VALID_CLASS_VARIANTS.get(self.class_name, set())
        if self.class_variant and self.class_variant not in allowed_variants:
            self.class_variant = ""

        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.display_name} ({self.class_name})"

    @property
    def role_display(self):
        return dict(self.Role.choices).get(self.role, self.role)

    @property
    def class_slug(self):
        return CLASS_COLORS.get(self.class_name, "unknown")

    @property
    def class_icon(self):
        # Giữ property này để template cũ không lỗi, nhưng không dùng icon phái nữa.
        return ""

    @property
    def variant_icon(self):
        return VARIANT_ICONS.get(self.class_variant, "")

    @property
    def has_variant(self):
        return self.class_name in VALID_CLASS_VARIANTS

    @property
    def class_label(self):
        if self.class_variant:
            return f"{self.class_name} · {self.class_variant}"
        return self.class_name


class WarEvent(models.Model):
    """
    Sự kiện bang chiến. Mỗi tuần có 1 event.
    - is_current=True: event đang được dùng cho check-in.
    - Chỉ có duy nhất 1 event is_current tại một thời điểm.
    """

    class Status(models.TextChoices):
        DRAFT = "draft", "Nháp"
        OPEN = "open", "Đang mở"
        CLOSED = "closed", "Đã đóng"
        ARCHIVED = "archived", "Lưu trữ"

    title = models.CharField("Tiêu đề", max_length=200)
    event_date = models.DateField("Ngày bang chiến")
    deadline_at = models.DateTimeField("Hạn báo danh", null=True, blank=True)
    status = models.CharField(
        "Trạng thái", max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    is_current = models.BooleanField("Event hiện tại", default=False)
    team_notes = models.JSONField("Ghi chú chiến thuật theo team", default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sự kiện bang chiến"
        verbose_name_plural = "Sự kiện bang chiến"
        ordering = ["-event_date"]
        indexes = [
            models.Index(fields=["is_current"]),
            models.Index(fields=["status"]),
        ]

    def save(self, *args, **kwargs):
        # Đảm bảo chỉ có 1 event is_current
        if self.is_current:
            WarEvent.objects.exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.title} ({self.event_date})"


class Attendance(models.Model):
    """
    Điểm danh của 1 member cho 1 war event.
    - BR1: Luôn lưu bằng member_id (ForeignKey), không lưu tên text.
    - BR6: UniqueConstraint war_event + member → mỗi member chỉ có 1 record/event.
    """

    class Status(models.TextChoices):
        JOINED = "joined", "Tham gia"
        ABSENT = "absent", "Không tham gia"

    class Source(models.TextChoices):
        WEB = "web", "Web (member tự báo)"
        ADMIN = "admin", "Admin"
        SYSTEM = "system", "Hệ thống"

    war_event = models.ForeignKey(
        WarEvent, on_delete=models.CASCADE, related_name="attendances", verbose_name="Sự kiện"
    )
    member = models.ForeignKey(
        Member, on_delete=models.CASCADE, related_name="attendances", verbose_name="Thành viên"
    )
    status = models.CharField("Trạng thái", max_length=20, choices=Status.choices)
    note = models.TextField("Ghi chú", blank=True)
    strategy_note = models.CharField("Ghi chú skill/chiến thuật cá nhân", max_length=120, blank=True)
    battle_team = models.CharField("Team xếp đội theo event", max_length=20, choices=Member.BattleTeam.choices, blank=True, default="")
    battle_position = models.PositiveSmallIntegerField("Vị trí xếp đội theo event", null=True, blank=True)
    # device_id lưu để track thiết bị (không phải bảo mật, chỉ để debug)
    device_id = models.CharField("Device ID", max_length=200, blank=True)
    source = models.CharField(
        "Nguồn", max_length=20, choices=Source.choices, default=Source.WEB
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Điểm danh"
        verbose_name_plural = "Điểm danh"
        constraints = [
            models.UniqueConstraint(
                fields=["war_event", "member"],
                name="unique_attendance_per_event",
            )
        ]
        indexes = [
            models.Index(fields=["war_event"]),
            models.Index(fields=["status"]),
            models.Index(fields=["war_event", "battle_team", "battle_position"]),
        ]

    def __str__(self):
        return f"{self.member.display_name} – {self.get_status_display()} ({self.war_event})"


class AttendanceAuditLog(models.Model):
    """
    Lịch sử thay đổi attendance.
    - BR7: Tạo log khi member đổi trạng thái.
    - BR8: actor_type=admin khi leader sửa.
    """

    class ActorType(models.TextChoices):
        MEMBER = "member", "Member"
        ADMIN = "admin", "Admin"
        SYSTEM = "system", "Hệ thống"

    attendance = models.ForeignKey(
        Attendance, on_delete=models.CASCADE, related_name="audit_logs"
    )
    war_event = models.ForeignKey(WarEvent, on_delete=models.CASCADE)
    member = models.ForeignKey(Member, on_delete=models.CASCADE)
    old_status = models.CharField(max_length=20, blank=True)
    new_status = models.CharField(max_length=20)
    old_note = models.TextField(blank=True)
    new_note = models.TextField(blank=True)
    device_id = models.CharField(max_length=200, blank=True)
    actor_type = models.CharField(
        max_length=20, choices=ActorType.choices, default=ActorType.MEMBER
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Lịch sử điểm danh"
        verbose_name_plural = "Lịch sử điểm danh"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"[{self.actor_type}] {self.member.display_name}: "
            f"{self.old_status} → {self.new_status}"
        )


class MemberRequest(models.Model):
    """
    Yêu cầu thêm thành viên mới.
    - BR4: Không tự động tạo Member chính thức.
    - BR5: Admin duyệt mới tạo Member từ request này.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Chờ duyệt"
        APPROVED = "approved", "Đã duyệt"
        REJECTED = "rejected", "Từ chối"

    requested_name = models.CharField("Tên nhân vật yêu cầu", max_length=100)
    class_name = models.CharField("Phái", max_length=50, choices=Member.ClassName.choices, blank=True)
    class_variant = models.CharField("Hệ/phân nhánh", max_length=50, choices=Member.ClassVariant.choices, blank=True)
    role = models.CharField("Role", max_length=20, blank=True)
    team = models.CharField("Đội", max_length=50, blank=True)
    note = models.TextField("Ghi chú", blank=True)
    status = models.CharField(
        "Trạng thái", max_length=20, choices=Status.choices, default=Status.PENDING
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Yêu cầu thêm thành viên"
        verbose_name_plural = "Yêu cầu thêm thành viên"
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        allowed_variants = VALID_CLASS_VARIANTS.get(self.class_name, set())
        if self.class_variant and self.class_variant not in allowed_variants:
            self.class_variant = ""
        super().save(*args, **kwargs)

    def __str__(self):
        return f"Request: {self.requested_name} ({self.get_status_display()})"
