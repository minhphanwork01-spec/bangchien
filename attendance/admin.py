"""
attendance/admin.py

Django Admin configuration cho bangcheck.
Leader/admin quản lý Member, WarEvent, Attendance, và dữ liệu nền.
"""

from django.contrib import admin
from .models import Member, WarEvent, Attendance, AttendanceAuditLog, MemberRequest


@admin.register(Member)
class MemberAdmin(admin.ModelAdmin):
    # Team/squad không còn khóa theo member; đội hình thật nằm trong Attendance theo từng event.
    list_display = ("display_name", "class_name", "class_variant", "active", "updated_at")
    list_filter = ("active", "class_name", "class_variant")
    search_fields = ("display_name", "search_name")
    readonly_fields = ("search_name", "created_at", "updated_at")
    list_editable = ("class_name", "class_variant", "active")
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

    class Media:
        js = ("admin/js/member_variant_filter.js",)


@admin.register(WarEvent)
class WarEventAdmin(admin.ModelAdmin):
    list_display = ("title", "event_date", "status", "is_current", "updated_at")
    list_filter = ("status", "is_current")
    list_editable = ("status", "is_current")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("-event_date",)
    fieldsets = (
        ("Thông tin event", {
            "fields": ("title", "event_date", "deadline_at", "status", "is_current")
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
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("member", "war_event", "status", "battle_team", "battle_position", "source", "updated_at")
    list_filter = ("war_event", "status", "battle_team", "source")
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
    list_filter = ("actor_type", "war_event")
    search_fields = ("member__display_name",)
    readonly_fields = (
        "attendance", "war_event", "member", "old_status", "new_status",
        "device_id", "actor_type", "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(MemberRequest)
class MemberRequestAdmin(admin.ModelAdmin):
    list_display = ("requested_name", "class_name", "class_variant", "status", "created_at")
    list_filter = ("status", "class_name", "class_variant")
    search_fields = ("requested_name",)
    list_editable = ("status",)
    readonly_fields = ("created_at", "updated_at")

    actions = ["approve_requests"]

    def approve_requests(self, request, queryset):
        """Bulk approve: tạo Member từ từng MemberRequest pending."""
        approved = 0
        for mr in queryset.filter(status=MemberRequest.Status.PENDING):
            Member.objects.create(
                display_name=mr.requested_name,
                class_name=mr.class_name,
                class_variant=mr.class_variant,
                note=mr.note,
                active=True,
            )
            mr.status = MemberRequest.Status.APPROVED
            mr.save()
            approved += 1
        self.message_user(request, f"Đã duyệt {approved} yêu cầu và tạo thành viên mới.")

    approve_requests.short_description = "Duyệt và tạo thành viên mới"

    class Media:
        js = ("admin/js/member_variant_filter.js",)
