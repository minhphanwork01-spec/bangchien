"""
attendance/models.py

Models cho hệ thống điểm danh bang chiến.
Thiết kế theo nguyên tắc: attendance luôn lưu bằng member_id, không lưu tên text.
"""

import unicodedata
from django.db import models
from django.utils import timezone


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

# Không dùng emoji làm icon (render khác nhau mỗi OS, nhìn "chatbot").
# Variant đã hiển thị trong class_label ("Thiết Y · Ngự"); giữ dict rỗng
# để property variant_icon không vỡ các payload cũ.
VARIANT_ICONS = {}

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
        PHA = "Phá", "Phá"
        NGU = "Ngự", "Ngự"
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
    team = models.CharField("Đội", max_length=50, blank=True)
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
            models.Index(fields=["display_name"], name="attendance__display_5e89d9_idx"),
            models.Index(fields=["search_name"], name="attendance__search__f7bdf3_idx"),
            models.Index(fields=["active"], name="attendance__active_395a22_idx"),
            models.Index(fields=["class_name"], name="attendance__class__95a4d4_idx"),
            models.Index(fields=["battle_team", "battle_position"], name="attendance__battle_7ec61d_idx"),
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
    Sự kiện hoạt động của bang.
    - event_type=war: Bang chiến, có squad/feedback.
    - event_type=scrim: Scrim, chỉ điểm danh đơn giản.
    - is_current=True được tách theo từng event_type.
    """

    class EventType(models.TextChoices):
        WAR = "war", "Bang chiến"
        SCRIM = "scrim", "Scrim"

    class Status(models.TextChoices):
        DRAFT = "draft", "Nháp"
        OPEN = "open", "Đang mở"
        CLOSED = "closed", "Đã đóng"
        ARCHIVED = "archived", "Lưu trữ"

    event_type = models.CharField("Loại sự kiện", max_length=20, choices=EventType.choices, default=EventType.WAR)
    title = models.CharField("Tiêu đề", max_length=200)
    event_date = models.DateField("Ngày bang chiến")
    deadline_at = models.DateTimeField("Hạn báo danh", null=True, blank=True)
    battle_start_at = models.DateTimeField("Giờ bắt đầu bang chiến", null=True, blank=True)
    status = models.CharField(
        "Trạng thái", max_length=20, choices=Status.choices, default=Status.DRAFT
    )
    is_current = models.BooleanField("Event hiện tại", default=False)
    team_notes = models.JSONField("Ghi chú chiến thuật theo team", default=dict, blank=True)

    @property
    def checkin_lock_at(self):
        """Mốc khóa sổ: deadline_at nếu leader set, không thì giờ đánh trận."""
        return self.deadline_at or self.battle_start_at

    @property
    def checkin_locked(self):
        """Đã quá giờ khóa sổ chưa. Cả hai mốc đều trống -> không bao giờ khóa."""
        from django.utils import timezone as _tz
        lock_at = self.checkin_lock_at
        return lock_at is not None and _tz.now() >= lock_at
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sự kiện bang chiến"
        verbose_name_plural = "Sự kiện bang chiến"
        ordering = ["-event_date"]
        indexes = [
            models.Index(fields=["is_current"], name="attendance__is_curr_bcd787_idx"),
            models.Index(fields=["status"], name="attendance__status_839ebf_idx"),
            models.Index(fields=["event_type", "is_current"], name="attendance_w_event__e5b58b_idx"),
            models.Index(fields=["event_type", "status"], name="attendance_w_event__60b7a3_idx"),
        ]

    def save(self, *args, **kwargs):
        # Đảm bảo mỗi loại sự kiện chỉ có 1 event is_current.
        # Bang chiến và Scrim có current riêng, không ghi đè nhau.
        if self.is_current:
            WarEvent.objects.filter(event_type=self.event_type).exclude(pk=self.pk).update(is_current=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.get_event_type_display()} – {self.title} ({self.event_date})"

    @property
    def feedback_start_at(self):
        """Mốc mở feedback. Nếu chưa set giờ cụ thể, fallback 19:00 ngày bang chiến."""
        if self.battle_start_at:
            return self.battle_start_at

        from datetime import datetime, time

        naive_dt = datetime.combine(self.event_date, time(19, 0))
        if timezone.is_naive(naive_dt):
            return timezone.make_aware(naive_dt, timezone.get_current_timezone())
        return naive_dt


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
    # PROTECT: chặn xoá Member còn lịch sử điểm danh (bảo toàn dữ liệu chuyên cần).
    # Member rời bang -> tắt active, KHÔNG xoá. Xem action "Cho rời bang" trong admin.
    member = models.ForeignKey(
        Member, on_delete=models.PROTECT, related_name="attendances", verbose_name="Thành viên"
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
            models.Index(fields=["war_event"], name="attendance__war_eve_3fafc5_idx"),
            models.Index(fields=["status"], name="attendance__status_132c06_idx"),
            models.Index(fields=["war_event", "battle_team", "battle_position"], name="att_war_team_pos_idx"),
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
        verbose_name = "Lịch sử thay đổi điểm danh"
        verbose_name_plural = "Lịch sử thay đổi điểm danh"
        ordering = ["-created_at"]

    def __str__(self):
        return (
            f"[{self.actor_type}] {self.member.display_name}: "
            f"{self.old_status} → {self.new_status}"
        )


class BattleFeedback(models.Model):
    """
    Feedback ẩn danh mềm sau bang chiến.
    Leader chỉ xem content/thời gian/event; audit hash chỉ dành cho server owner/dev khi cần.
    """

    war_event = models.ForeignKey(
        WarEvent,
        on_delete=models.CASCADE,
        related_name="feedbacks",
        verbose_name="Sự kiện bang chiến",
    )
    content = models.TextField("Nội dung feedback")
    device_id_hash = models.CharField("Device hash", max_length=64, blank=True, db_index=True)
    member_id_hash = models.CharField("Member hash", max_length=64, blank=True)
    ip_hash = models.CharField("IP hash", max_length=64, blank=True)
    user_agent_hash = models.CharField("User-Agent hash", max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Feedback bang chiến"
        verbose_name_plural = "Feedback bang chiến"
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["war_event", "device_id_hash"],
                name="unique_feedback_per_device_event",
            )
        ]
        indexes = [
            models.Index(fields=["war_event", "created_at"], name="att_feedback_event_time_idx"),
        ]

    def __str__(self):
        return f"Feedback {self.war_event} – {self.created_at:%d/%m %H:%M}"

    @property
    def short_content(self):
        text = (self.content or "").strip()
        return text[:80] + ("..." if len(text) > 80 else "")



class MemberRequest(models.Model):
    """
    Yêu cầu liên quan đến thành viên.

    - request_type=add: đề nghị tạo nhân vật mới.
    - request_type=update: đề nghị đổi tên/phái cho Member hiện có.
    - Member chỉ được tạo/cập nhật sau khi leader duyệt.
    - Dữ liệu cũ và người/thời gian xử lý được giữ lại để audit.
    """

    class RequestType(models.TextChoices):
        ADD = "add", "Tạo mới"
        UPDATE = "update", "Chỉnh thông tin"

    class Status(models.TextChoices):
        PENDING = "pending", "Chờ duyệt"
        APPROVED = "approved", "Đã duyệt"
        REJECTED = "rejected", "Từ chối"

    request_type = models.CharField(
        "Loại yêu cầu",
        max_length=20,
        choices=RequestType.choices,
        default=RequestType.ADD,
    )
    target_member = models.ForeignKey(
        Member,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="change_requests",
        verbose_name="Nhân vật cần chỉnh",
    )

    # requested_* là dữ liệu đề xuất. Với request tạo mới, đây là dữ liệu member mới.
    requested_name = models.CharField("Tên nhân vật đề xuất", max_length=100)
    class_name = models.CharField(
        "Phái đề xuất",
        max_length=50,
        choices=Member.ClassName.choices,
        blank=True,
    )
    class_variant = models.CharField(
        "Hệ/phân nhánh đề xuất",
        max_length=50,
        choices=Member.ClassVariant.choices,
        blank=True,
    )

    # Snapshot dữ liệu trước khi chỉnh, để audit vẫn còn ngay cả khi Member đổi sau đó.
    original_name = models.CharField("Tên ban đầu", max_length=100, blank=True)
    original_class_name = models.CharField("Phái ban đầu", max_length=50, blank=True)
    original_class_variant = models.CharField(
        "Hệ/phân nhánh ban đầu",
        max_length=50,
        blank=True,
    )

    role = models.CharField("Role", max_length=20, blank=True)
    team = models.CharField("Đội", max_length=50, blank=True)
    note = models.TextField("Ghi chú của người gửi", blank=True)
    status = models.CharField(
        "Trạng thái",
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
    )

    reviewed_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_member_requests",
        verbose_name="Người xử lý",
    )
    reviewed_at = models.DateTimeField("Xử lý lúc", null=True, blank=True)
    review_note = models.TextField("Ghi chú xử lý", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Yêu cầu thành viên"
        verbose_name_plural = "Yêu cầu thành viên"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["request_type", "status"], name="att_mreq_type_status_idx"),
            models.Index(fields=["target_member", "status"], name="att_mreq_target_status_idx"),
        ]

    def save(self, *args, **kwargs):
        allowed_variants = VALID_CLASS_VARIANTS.get(self.class_name, set())
        if self.class_variant and self.class_variant not in allowed_variants:
            self.class_variant = ""

        if self.request_type == self.RequestType.UPDATE and self.target_member_id:
            # Chỉ tự chụp snapshot khi request mới chưa có snapshot.
            if not self.original_name:
                self.original_name = self.target_member.display_name
            if not self.original_class_name:
                self.original_class_name = self.target_member.class_name
            if not self.original_class_variant:
                self.original_class_variant = self.target_member.class_variant

        super().save(*args, **kwargs)

    @property
    def is_update(self):
        return self.request_type == self.RequestType.UPDATE

    @property
    def has_name_change(self):
        return self.is_update and self.requested_name != self.original_name

    @property
    def has_class_change(self):
        return self.is_update and (
            self.class_name != self.original_class_name
            or self.class_variant != self.original_class_variant
        )

    def __str__(self):
        return (
            f"{self.get_request_type_display()}: "
            f"{self.requested_name} ({self.get_status_display()})"
        )



class AdminActionLog(models.Model):
    """
    Nhật ký thao tác trong khu quản trị (Django admin + action của leader).

    Khác gì với LogEntry sẵn có của Django:
    - LogEntry chỉ ghi "đã đổi trường Tên hiển thị", KHÔNG lưu giá trị cũ.
    - Bảng này lưu cả giá trị TRƯỚC và SAU của từng trường (cột changes),
      cộng dấu vết thiết bị (IP, trình duyệt, mã browser theo cookie).

    Mã browser_id là cookie ngẫu nhiên gắn theo từng trình duyệt: hai người
    dùng CHUNG một account admin nhưng khác máy sẽ có browser_id khác nhau,
    nên vẫn tách được ai là ai — dù account giống hệt.
    """

    class Action(models.TextChoices):
        CREATE = "create", "Tạo mới"
        UPDATE = "update", "Chỉnh sửa"
        DELETE = "delete", "Xoá"

    actor = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="admin_action_logs",
        verbose_name="Tài khoản",
    )
    actor_username = models.CharField("Tên đăng nhập", max_length=150, blank=True)
    action = models.CharField("Hành động", max_length=20, choices=Action.choices)
    object_type = models.CharField("Loại đối tượng", max_length=100, blank=True)
    object_id = models.CharField("ID đối tượng", max_length=50, blank=True)
    object_repr = models.CharField("Đối tượng", max_length=250, blank=True)
    # {"display_name": ["Tên cũ", "Tên mới"], "active": [true, false], ...}
    changes = models.JSONField("Thay đổi", default=dict, blank=True)
    ip_address = models.CharField("IP", max_length=64, blank=True)
    user_agent = models.CharField("Thiết bị/trình duyệt", max_length=300, blank=True)
    browser_id = models.CharField("Mã trình duyệt", max_length=64, blank=True)
    note = models.CharField("Ghi chú", max_length=250, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Nhật ký quản trị"
        verbose_name_plural = "Nhật ký quản trị"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["-created_at"]),
            models.Index(fields=["object_type", "object_id"]),
            models.Index(fields=["actor_username"]),
        ]

    def __str__(self):
        return f"{self.actor_username} {self.get_action_display()} {self.object_repr}"

    @property
    def device_label(self):
        """Rút gọn User-Agent thành nhãn dễ đọc: 'Chrome · Windows'."""
        ua = self.user_agent or ""
        if not ua:
            return "—"
        if "iPhone" in ua or "iPad" in ua:
            os_name = "iOS"
        elif "Android" in ua:
            os_name = "Android"
        elif "Windows" in ua:
            os_name = "Windows"
        elif "Mac OS" in ua or "Macintosh" in ua:
            os_name = "macOS"
        elif "Linux" in ua:
            os_name = "Linux"
        else:
            os_name = "Khác"
        if "Edg/" in ua:
            browser = "Edge"
        elif "Chrome/" in ua and "Chromium" not in ua:
            browser = "Chrome"
        elif "Firefox/" in ua:
            browser = "Firefox"
        elif "Safari/" in ua and "Chrome/" not in ua:
            browser = "Safari"
        else:
            browser = "Khác"
        return f"{browser} · {os_name}"

    @property
    def browser_short(self):
        """6 ký tự đầu của mã trình duyệt — đủ để phân biệt máy, đủ ngắn để đọc."""
        return (self.browser_id or "")[:6] or "—"
