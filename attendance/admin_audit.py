"""
Ghi nhật ký thao tác quản trị: ai sửa gì, giá trị trước/sau, từ thiết bị nào.

Vì sao cần, khi Django đã có LogEntry sẵn:
- LogEntry chỉ ghi TÊN trường bị đổi ("đã đổi Tên hiển thị"), không lưu giá
  trị cũ. Muốn biết "tên trước đó là gì" thì chịu.
- LogEntry không ghi IP / trình duyệt, nên khi nhiều người dùng chung một
  account admin thì không tách được ai là ai.

Module này bù đúng hai chỗ đó.
"""
import uuid

from django.contrib.auth import get_user_model

from .models import AdminActionLog

# Cookie gắn mã ngẫu nhiên cho từng trình duyệt vào khu quản trị.
ADMIN_BROWSER_COOKIE = "bc_admin_browser"
ADMIN_BROWSER_MAX_AGE = 60 * 60 * 24 * 365 * 2  # 2 năm

# Trường không bao giờ ghi vào log (bí mật hoặc nhiễu).
SKIP_FIELDS = {"password", "search_name", "created_at", "updated_at"}


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")


def get_browser_id(request):
    return request.COOKIES.get(ADMIN_BROWSER_COOKIE, "")


def snapshot(obj):
    """Chụp giá trị các trường đơn giản của một bản ghi để so sánh trước/sau."""
    if obj is None or obj.pk is None:
        return {}
    data = {}
    for field in obj._meta.fields:
        name = field.name
        if name in SKIP_FIELDS:
            continue
        try:
            value = getattr(obj, field.attname, None)
        except Exception:
            continue
        # Chỉ giữ kiểu JSON-an toàn; còn lại đổi sang chuỗi.
        if value is None or isinstance(value, (str, int, float, bool)):
            data[name] = value
        else:
            data[name] = str(value)
    return data


def diff(before, after):
    """Trả {field: [cũ, mới]} cho các trường thực sự đổi."""
    changes = {}
    for key, new_value in after.items():
        old_value = before.get(key)
        if old_value != new_value:
            changes[key] = [old_value, new_value]
    return changes


def write_log(request, action, obj=None, changes=None, note="", object_type=""):
    """Ghi một dòng nhật ký. Không bao giờ làm vỡ luồng chính nếu lỗi."""
    try:
        user = getattr(request, "user", None)
        is_authed = bool(user and getattr(user, "is_authenticated", False))
        AdminActionLog.objects.create(
            actor=user if is_authed else None,
            actor_username=getattr(user, "username", "") if is_authed else "",
            action=action,
            object_type=object_type or (obj._meta.verbose_name if obj is not None else ""),
            object_id=str(getattr(obj, "pk", "") or ""),
            object_repr=str(obj)[:250] if obj is not None else "",
            changes=changes or {},
            ip_address=get_client_ip(request)[:64],
            user_agent=request.META.get("HTTP_USER_AGENT", "")[:300],
            browser_id=get_browser_id(request)[:64],
            note=note[:250],
        )
    except Exception:  # noqa: BLE001 — log hỏng không được làm hỏng thao tác của leader
        pass


class AuditedModelAdmin:
    """
    Mixin cho ModelAdmin: tự ghi nhật ký khi thêm / sửa / xoá trong admin,
    kèm giá trị trước-sau và dấu vết thiết bị.

    Dùng: class MemberAdmin(AuditedModelAdmin, admin.ModelAdmin)
    """

    def save_model(self, request, obj, form, change):
        before = {}
        if change and obj.pk:
            try:
                before = snapshot(self.model.objects.get(pk=obj.pk))
            except self.model.DoesNotExist:
                before = {}
        super().save_model(request, obj, form, change)
        after = snapshot(obj)
        if change:
            changed = diff(before, after)
            if changed:
                write_log(request, AdminActionLog.Action.UPDATE, obj, changed)
        else:
            write_log(
                request,
                AdminActionLog.Action.CREATE,
                obj,
                {k: [None, v] for k, v in after.items() if v not in (None, "", False)},
            )

    def delete_model(self, request, obj):
        write_log(
            request,
            AdminActionLog.Action.DELETE,
            obj,
            {k: [v, None] for k, v in snapshot(obj).items()},
        )
        super().delete_model(request, obj)

    def delete_queryset(self, request, queryset):
        for obj in queryset:
            write_log(
                request,
                AdminActionLog.Action.DELETE,
                obj,
                {k: [v, None] for k, v in snapshot(obj).items()},
            )
        super().delete_queryset(request, queryset)


class AdminBrowserIdMiddleware:
    """
    Gán mã ngẫu nhiên cho mỗi trình duyệt vào khu quản trị/leader.

    Mục đích: nhiều người dùng CHUNG một account admin thì log chỉ thấy một
    tên. Mã này ổn định theo từng máy (khác IP vốn đổi liên tục), nên vẫn
    phân biệt được "máy nào" đã thao tác.

    Chỉ set cookie cho user đã đăng nhập là staff — không đụng gì tới member.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        user = getattr(request, "user", None)
        if user is not None and getattr(user, "is_staff", False):
            if not request.COOKIES.get(ADMIN_BROWSER_COOKIE):
                from django.conf import settings

                response.set_cookie(
                    ADMIN_BROWSER_COOKIE,
                    uuid.uuid4().hex,
                    max_age=ADMIN_BROWSER_MAX_AGE,
                    httponly=True,
                    samesite="Lax",
                    secure=not settings.DEBUG,
                )
        return response
