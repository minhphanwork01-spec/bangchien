"""
attendance/admin.py

Django Admin configuration cho bangcheck.
Leader/admin quản lý Member, WarEvent, Attendance, và dữ liệu nền.
"""

from django.contrib import admin
from .admin_audit import AuditedModelAdmin, write_log
from .models import AdminActionLog, BattleFeedback, Member, WarEvent, Attendance, AttendanceAuditLog, MemberRequest
from .services import MemberRequestError, approve_member_request, reject_member_request


@admin.register(Member)
class MemberAdmin(AuditedModelAdmin, admin.ModelAdmin):
    # Team/squad không còn khóa theo member; đội hình thật nằm trong Attendance theo từng event.
    #
    # THÀNH VIÊN OUT BANG: KHÔNG dùng nút Delete. Chọn thành viên rồi dùng action
    # "Cho rời bang (tắt hoạt động)" — lịch sử điểm danh của họ được giữ nguyên
    # cho thống kê chuyên cần. Delete member còn lịch sử sẽ bị hệ thống chặn (PROTECT).
    list_display = ("display_name", "class_name", "class_variant", "active", "updated_at")
    list_filter = ("active", "class_name", "class_variant")
    search_fields = ("display_name", "search_name")
    readonly_fields = ("search_name", "created_at", "updated_at")
    list_editable = ("class_name", "class_variant", "active")
    actions = ("action_leave_guild", "action_reactivate")

    @admin.action(description="Cho rời bang (tắt hoạt động, giữ lịch sử điểm danh)")
    def action_leave_guild(self, request, queryset):
        # Duyệt từng bản ghi + save() thay vì queryset.update(): update() ghi
        # thẳng xuống DB, BỎ QUA save() nên updated_at không đổi và không có
        # dấu vết nào. Vài chục member thì chi phí không đáng kể, đổi lại
        # truy vết được ai cho ai rời bang lúc nào.
        count = 0
        for member in queryset.filter(active=True):
            member.active = False
            member.save(update_fields=["active", "updated_at"])
            write_log(
                request,
                AdminActionLog.Action.UPDATE,
                member,
                {"active": [True, False]},
                note="Cho rời bang",
            )
            count += 1
        self.message_user(
            request,
            f"Đã cho {count} thành viên rời bang. Lịch sử điểm danh được giữ nguyên; "
            "cần quay lại bang thì dùng action Kích hoạt lại.",
        )

    @admin.action(description="Kích hoạt lại (quay lại bang)")
    def action_reactivate(self, request, queryset):
        count = 0
        for member in queryset.filter(active=False):
            member.active = True
            member.save(update_fields=["active", "updated_at"])
            write_log(
                request,
                AdminActionLog.Action.UPDATE,
                member,
                {"active": [False, True]},
                note="Kích hoạt lại",
            )
            count += 1
        self.message_user(request, f"Đã kích hoạt lại {count} thành viên.")
    fieldsets = (
        ("Thông tin cơ bản", {
            "fields": ("display_name", "search_name", "class_name", "class_variant")
        }),
        ("Ghi chú", {
            "fields": ("note",)
        }),
        ("Trạng thái", {
            "fields": ("active", "created_at", "updated_at")
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)

    def changelist_view(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context["subtitle"] = (
            "Thành viên out bang: chọn ✓ rồi dùng action \"Cho rời bang\" — "
            "KHÔNG bấm Delete (hệ thống sẽ chặn nếu còn lịch sử điểm danh)."
        )
        return super().changelist_view(request, extra_context=extra_context)

    class Media:
        js = ("admin/js/member_variant_filter.js",)


@admin.register(WarEvent)
class WarEventAdmin(AuditedModelAdmin, admin.ModelAdmin):
    list_display = ("event_type", "title", "event_date", "battle_start_at", "status", "is_current", "updated_at")
    list_filter = ("event_type", "status", "is_current")
    list_editable = ("status", "is_current")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-event_date",)
    fieldsets = (
        ("Thông tin event", {
            "fields": ("event_type", "title", "event_date", "deadline_at", "battle_start_at", "status", "is_current")
        }),
        ("Ghi chú chiến thuật theo team", {
            "fields": ("team_notes",),
            "description": "Có thể sửa nhanh hơn ở trang Leader → Xếp đội hình.",
        }),
        ("Khác", {
            "fields": ("created_at", "updated_at")
        }),
    )

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)


class AttendanceAuditLogInline(admin.TabularInline):
    model = AttendanceAuditLog
    extra = 0
    readonly_fields = ("old_status", "new_status", "actor_type", "device_id", "created_at")
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Attendance)
class AttendanceAdmin(AuditedModelAdmin, admin.ModelAdmin):
    list_display = ("member", "war_event", "status", "battle_team", "battle_position", "source", "updated_at")
    list_filter = ("war_event__event_type", "war_event", "status", "battle_team", "source")
    search_fields = ("member__display_name",)
    readonly_fields = ("device_id", "created_at", "updated_at")
    inlines = [AttendanceAuditLogInline]
    raw_id_fields = ("member", "war_event")
    fieldsets = (
        ("Điểm danh", {
            "fields": ("war_event", "member", "status")
        }),
        ("Xếp đội theo event", {
            "fields": ("battle_team", "battle_position", "strategy_note")
        }),
        ("Hệ thống", {
            "fields": ("source", "device_id", "created_at", "updated_at")
        }),
    )


@admin.register(AttendanceAuditLog)
class AttendanceAuditLogAdmin(admin.ModelAdmin):
    list_display = ("member", "war_event", "old_status", "new_status", "actor_type", "created_at")
    list_filter = ("actor_type", "war_event__event_type", "war_event")
    search_fields = ("member__display_name",)
    readonly_fields = (
        "attendance", "war_event", "member", "old_status", "new_status",
        "device_id", "actor_type", "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(BattleFeedback)
class BattleFeedbackAdmin(AuditedModelAdmin, admin.ModelAdmin):
    """Leader/admin xem nội dung feedback. Audit hash không hiển thị trong Admin UI."""
    list_display = ("war_event", "short_content", "created_at", "updated_at")
    list_filter = ("war_event__event_type", "war_event", "created_at")
    search_fields = ("content", "war_event__title")
    readonly_fields = ("created_at", "updated_at")
    fieldsets = (
        ("Feedback", {
            "fields": ("war_event", "content")
        }),
        ("Thời gian", {
            "fields": ("created_at", "updated_at")
        }),
    )


@admin.register(MemberRequest)
class MemberRequestAdmin(AuditedModelAdmin, admin.ModelAdmin):
    list_display = (
        "request_type",
        "requested_name",
        "target_member",
        "class_name",
        "status",
        "created_at",
        "reviewed_by",
        "reviewed_at",
    )
    list_filter = ("request_type", "status", "class_name", "class_variant")
    search_fields = (
        "requested_name",
        "original_name",
        "target_member__display_name",
        "note",
        "review_note",
    )
    readonly_fields = (
        "original_name",
        "original_class_name",
        "original_class_variant",
        "created_at",
        "updated_at",
        "reviewed_by",
        "reviewed_at",
    )
    raw_id_fields = ("target_member",)
    actions = ["approve_requests", "reject_requests"]

    fieldsets = (
        ("Yêu cầu", {
            "fields": (
                "request_type",
                "target_member",
                "requested_name",
                "class_name",
                "class_variant",
                "note",
                "status",
            )
        }),
        ("Thông tin ban đầu", {
            "fields": (
                "original_name",
                "original_class_name",
                "original_class_variant",
            )
        }),
        ("Xử lý", {
            "fields": (
                "reviewed_by",
                "reviewed_at",
                "review_note",
            )
        }),
        ("Thời gian", {
            "fields": ("created_at", "updated_at")
        }),
    )

    def approve_requests(self, request, queryset):
        approved = 0
        errors = []
        for member_request in queryset.filter(status=MemberRequest.Status.PENDING):
            try:
                approve_member_request(
                    member_request.pk,
                    request.user,
                    review_note="Duyệt từ Django Admin.",
                )
            except MemberRequestError as exc:
                errors.append(f"{member_request.pk}: {exc}")
            else:
                approved += 1

        if approved:
            self.message_user(request, f"Đã duyệt {approved} yêu cầu.")
        if errors:
            self.message_user(
                request,
                "Không thể duyệt: " + "; ".join(errors),
                level="error",
            )

    approve_requests.short_description = "Duyệt yêu cầu đã chọn"

    def reject_requests(self, request, queryset):
        rejected = 0
        for member_request in queryset.filter(status=MemberRequest.Status.PENDING):
            try:
                reject_member_request(
                    member_request.pk,
                    request.user,
                    review_note="Từ chối từ Django Admin.",
                )
            except MemberRequestError:
                continue
            rejected += 1
        self.message_user(request, f"Đã từ chối {rejected} yêu cầu.")

    reject_requests.short_description = "Từ chối yêu cầu đã chọn"

    class Media:
        js = ("admin/js/member_variant_filter.js",)




@admin.register(AdminActionLog)
class AdminActionLogAdmin(admin.ModelAdmin):
    """Nhật ký quản trị — chỉ đọc, không cho sửa/xoá để giữ tính toàn vẹn."""

    list_display = ("created_at", "actor_username", "action", "object_type", "object_repr", "device_label", "browser_short")
    list_filter = ("action", "object_type", "actor_username")
    search_fields = ("actor_username", "object_repr", "object_id", "note")
    readonly_fields = (
        "actor", "actor_username", "action", "object_type", "object_id",
        "object_repr", "changes", "ip_address", "user_agent", "browser_id",
        "note", "created_at",
    )
    date_hierarchy = "created_at"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
