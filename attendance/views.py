"""
attendance/views.py

Views cho bangcheck – hệ thống điểm danh bang chiến.

Nguyên tắc cốt lõi:
- BR1: Attendance luôn lưu bằng member_id (ForeignKey), không bao giờ lưu text name.
- BR2: Search text chỉ để lọc hiển thị, không tạo record từ text input.
- BR6: update_or_create đảm bảo 1 attendance/member/event.
- BR7: Tạo audit log khi trạng thái thay đổi (actor_type=member).
- BR8: Tạo audit log khi leader sửa (actor_type=admin).
- BR9/10: Cookie chỉ là UX convenience, không phải bảo mật.
"""

import csv
import hashlib
import hmac
import json
import uuid

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db import transaction
from django.db.models import Count, Max, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.utils import timezone
from django_ratelimit.decorators import ratelimit

from . import ops, stats

from .forms import MemberRequestForm, MemberUpdateRequestForm
from .models import AdminActionLog, Attendance, AttendanceAuditLog, BattleFeedback, Member, MemberRequest, WarEvent, normalize_search_name
from .services import MemberRequestError, approve_member_request, reject_member_request

# Cookie key để lưu member đã chọn
MEMBER_COOKIE_KEY = "selected_member_id"
# Cookie mềm để nhận diện browser/device cho feedback/audit UX. Không phải hardware ID.
DEVICE_COOKIE_KEY = "bangcheck_device_id"
# 30 ngày
COOKIE_MAX_AGE = 60 * 60 * 24 * 30
# 1 năm cho device cookie
DEVICE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365

# Mở feedback sau 19:00 ngày bang chiến nếu event chưa cấu hình battle_start_at.
DEFAULT_FEEDBACK_HOUR = 19
DEFAULT_FEEDBACK_MINUTE = 0

# Cấu hình đội hình bang chiến kiểu Nghịch Thủy Hàn.
# Mỗi tab có 30 ô = 5 nhóm nhỏ, mỗi nhóm là 1 cột 6 người theo format game.
PARTY_TEAMS = {
    "defense": {
        "label": "Team thủ",
        "short": "Thủ",
        "capacity": 30,
        "cols": 5,
        "group_size": 6,
        "description": "Đội thủ / thủ trụ",
    },
    "offense": {
        "label": "Team công",
        "short": "Công",
        "capacity": 30,
        "cols": 5,
        "group_size": 6,
        "description": "Đội công",
    },
    "mid": {
        "label": "Team mid",
        "short": "Mid",
        "capacity": 30,
        "cols": 5,
        "group_size": 6,
        "description": "Đội mid",
    },
    "supply": {
        "label": "Team vật tư",
        "short": "Vật tư",
        "capacity": 30,
        "cols": 5,
        "group_size": 6,
        "description": "Đội vật tư / hậu cần",
    },
}


def is_staff_user(user):
    """Kiểm tra user có phải staff không (cho leader area)."""
    return user.is_active and user.is_staff


def normalize_event_type(event_type):
    """Chuẩn hóa loại sự kiện; mặc định là bang chiến."""
    valid_types = {choice[0] for choice in WarEvent.EventType.choices}
    return event_type if event_type in valid_types else WarEvent.EventType.WAR


def get_event_type_label(event_type):
    return dict(WarEvent.EventType.choices).get(normalize_event_type(event_type), "Bang chiến")


def get_current_event(event_type=WarEvent.EventType.WAR):
    """
    Lấy event hiện tại đang mở theo từng loại sự kiện.
    Bang chiến và Scrim có current riêng, không ghi đè nhau.
    """
    event_type = normalize_event_type(event_type)
    event = WarEvent.objects.filter(
        event_type=event_type,
        is_current=True,
        status=WarEvent.Status.OPEN,
    ).first()
    if event:
        return event
    return WarEvent.objects.filter(
        event_type=event_type,
        status=WarEvent.Status.OPEN,
    ).order_by("-event_date", "-id").first()


def get_member_from_cookie(request):
    """
    Đọc member đã chọn từ cookie. Cookie chỉ là UX convenience, không phải xác thực.
    Nếu cookie mất/sai/member inactive thì trả về None để user chọn lại.
    """
    member_id = request.COOKIES.get(MEMBER_COOKIE_KEY)
    if not member_id:
        return None

    try:
        return Member.objects.get(id=int(member_id), active=True)
    except (Member.DoesNotExist, ValueError, TypeError):
        return None


def get_or_create_device_id(request):
    """
    Lấy hoặc tạo browser/device token mềm bằng cookie.
    Token này không phải hardware ID; chỉ dùng để hạn chế feedback spam và audit mềm.
    """
    device_id = request.COOKIES.get(DEVICE_COOKIE_KEY)
    if device_id:
        return device_id, False
    return uuid.uuid4().hex, True


def set_device_cookie(response, device_id):
    """Set device cookie an toàn vừa đủ cho local/dev và PythonAnywhere HTTPS."""
    response.set_cookie(
        DEVICE_COOKIE_KEY,
        device_id,
        max_age=DEVICE_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
    )
    return response


def hash_identifier(value):
    """
    HMAC-SHA256 với salt riêng (FEEDBACK_HASH_SALT, fallback SECRET_KEY)
    để không lưu raw member/device/ip trong feedback.
    """
    if value is None or value == "":
        return ""
    salt = getattr(settings, "FEEDBACK_HASH_SALT", settings.SECRET_KEY)
    return hmac.new(salt.encode("utf-8"), str(value).encode("utf-8"), hashlib.sha256).hexdigest()


RATE_LIMIT_MESSAGE = "Bạn thao tác quá nhanh. Vui lòng chờ một lát rồi thử lại."


def safe_next_redirect(request, fallback_url_name):
    """
    Chỉ cho phép redirect nội bộ từ tham số ?next / POST next.
    Chặn open redirect sang domain ngoài.
    """
    target = request.POST.get("next") or request.GET.get("next") or ""
    if target and url_has_allowed_host_and_scheme(
        target, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return redirect(target)
    return redirect(fallback_url_name)


def get_client_ip(request):
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "")



def get_event_feedback_start_at(event):
    """Mốc mở feedback của event: battle_start_at hoặc event_date 19:00."""
    if event.battle_start_at:
        return event.battle_start_at

    from datetime import datetime, time

    naive_dt = datetime.combine(event.event_date, time(DEFAULT_FEEDBACK_HOUR, DEFAULT_FEEDBACK_MINUTE))
    if timezone.is_naive(naive_dt):
        return timezone.make_aware(naive_dt, timezone.get_current_timezone())
    return naive_dt


def get_feedback_event():
    """
    Event nhận feedback: event gần nhất đã đến giờ bang chiến.
    - Nếu hôm nay sau 19:00 của event current thì feedback gắn event hôm nay.
    - Nếu trước 19:00, fallback event gần nhất trước đó đã diễn ra.
    - Không cần user chọn event.
    """
    now = timezone.now()
    today = timezone.localdate()
    events = WarEvent.objects.filter(event_type=WarEvent.EventType.WAR, event_date__lte=today).order_by("-event_date", "-id")
    for event in events:
        if get_event_feedback_start_at(event) <= now:
            return event
    return None


def get_existing_feedback_for_request(request, event, device_id):
    device_hash = hash_identifier(device_id)
    if not device_hash:
        return None
    return BattleFeedback.objects.filter(war_event=event, device_id_hash=device_hash).first()


def create_audit_log(attendance, new_status, device_id, actor_type):
    """
    Tạo AttendanceAuditLog khi trạng thái điểm danh thay đổi.
    Attendance.note đã được bỏ khỏi UX, nên audit chỉ theo dõi status.
    """
    old_status = attendance.status

    if old_status == new_status:
        return False

    AttendanceAuditLog.objects.create(
        attendance=attendance,
        war_event=attendance.war_event,
        member=attendance.member,
        old_status=old_status,
        new_status=new_status,
        old_note="",
        new_note="",
        device_id=device_id,
        actor_type=actor_type,
    )
    return True


def build_attendance_summary(event):
    """
    Tính tổng số theo trạng thái cho một event.
    Chỉ còn 2 trạng thái check-in: joined / absent.
    no_response = active members chưa báo danh.
    """
    all_active_members = Member.objects.filter(active=True)
    attendances = Attendance.objects.filter(war_event=event).select_related("member")
    attendance_map = {a.member_id: a for a in attendances}

    counts = {
        "joined": 0,
        "absent": 0,
        "no_response": 0,
        "total": all_active_members.count(),
    }

    for member in all_active_members:
        att = attendance_map.get(member.id)
        if att and att.status in counts:
            counts[att.status] += 1
        else:
            counts["no_response"] += 1

    return counts, attendance_map


def get_party_available_attendances(event):
    """
    Trả về attendance có thể xếp đội: chỉ người đã báo Tham gia.
    Người absent/no_response không vào pool kéo-thả để tránh xếp nhầm.
    """
    return (
        Attendance.objects.filter(war_event=event, status=Attendance.Status.JOINED, member__active=True)
        .select_related("member")
        .order_by("member__class_name", "member__display_name")
    )


def get_party_available_members(event):
    """
    Backward-compatible helper cho nơi cũ còn gọi.
    """
    attendances = list(get_party_available_attendances(event))
    return [att.member for att in attendances], {att.member_id: att for att in attendances}


def member_to_party_payload(member, attendance=None):
    """Payload JSON-safe để render chip trong board."""
    return {
        "id": member.id,
        "display_name": member.display_name,
        "class_name": member.class_name,
        "class_variant": member.class_variant,
        "class_label": member.class_label,
        "class_slug": member.class_slug,
        "variant_icon": member.variant_icon,
        "battle_team": attendance.battle_team if attendance else "",
        "battle_position": attendance.battle_position if attendance else None,
        "attendance_status": attendance.status if attendance else "",
        "strategy_note": attendance.strategy_note if attendance else "",
    }


def build_party_boards(event):
    """
    Build dữ liệu squad/party board cho cả leader page và public page.
    Vị trí squad lưu theo Attendance, tức là thay đổi theo từng event/tuần.
    """
    attendances = list(get_party_available_attendances(event))
    attendance_map = {att.member_id: att for att in attendances}

    boards = {}
    assigned_ids = set()

    for team_key, cfg in PARTY_TEAMS.items():
        capacity = cfg["capacity"]
        cells = [None] * capacity

        assigned = [
            att for att in attendances
            if att.battle_team == team_key and att.battle_position
        ]
        assigned.sort(key=lambda att: att.battle_position or 999)

        for att in assigned:
            pos = int(att.battle_position or 0)
            if 1 <= pos <= capacity and cells[pos - 1] is None:
                cells[pos - 1] = member_to_party_payload(att.member, att)
                assigned_ids.add(att.member_id)

        rows = []
        cols = cfg["cols"]
        group_size = cfg.get("group_size")

        if group_size:
            # Render theo format game: mỗi cột là 1 party nhỏ 6 người.
            # Row 1: 1, 7, 13, 19, 25
            # Row 2: 2, 8, 14, 20, 26 ...
            for row_idx in range(group_size):
                row = []
                for col_idx in range(cols):
                    position = col_idx * group_size + row_idx + 1
                    if position <= capacity:
                        row.append({"position": position, "member": cells[position - 1]})
                rows.append(row)
        else:
            for idx in range(0, capacity, cols):
                row = []
                for offset, member_payload in enumerate(cells[idx: idx + cols], start=1):
                    row.append({"position": idx + offset, "member": member_payload})
                rows.append(row)

        boards[team_key] = {
            **cfg,
            "key": team_key,
            "rows": rows,
            "count": sum(1 for c in cells if c),
            "note": (event.team_notes or {}).get(team_key, ""),
        }

    unassigned = [
        member_to_party_payload(att.member, att)
        for att in attendances
        if att.member_id not in assigned_ids
    ]

    return boards, unassigned


def get_team_notes(event):
    notes = event.team_notes or {}
    return {key: notes.get(key, "") for key in PARTY_TEAMS}


# ─────────────────────────────────────────────
# Public / Member Views
# ─────────────────────────────────────────────


def checkin_home_view(request):
    """
    GET /checkin/
    Trang chọn luồng điểm danh: Bang chiến hoặc Scrim.
    """
    war_event = get_current_event(WarEvent.EventType.WAR)
    scrim_event = get_current_event(WarEvent.EventType.SCRIM)
    return render(
        request,
        "checkin_home.html",
        {
            "war_event": war_event,
            "scrim_event": scrim_event,
            "feedback_event": get_feedback_event(),
        },
    )


def checkin_view(request, event_type=WarEvent.EventType.WAR):
    """
    GET /checkin/<event_type>/
    - Nếu chưa có member trong cookie: hiển thị màn hình chọn nhân vật.
    - Nếu đã có member hợp lệ: hiển thị form điểm danh cho đúng loại event.
    """
    event_type = normalize_event_type(event_type)
    member = get_member_from_cookie(request)
    event = get_current_event(event_type)

    if member is None:
        members_qs = Member.objects.filter(active=True).order_by("display_name")
        members_data = [
            {
                "id": m.id,
                "display_name": m.display_name,
                "search_name": m.search_name,
                "class_name": m.class_name,
                "class_variant": m.class_variant,
                "class_label": m.class_label,
                "class_slug": m.class_slug,
                "variant_icon": m.variant_icon,
            }
            for m in members_qs
        ]
        return render(
            request,
            "checkin_select.html",
            {
                "members_data": members_data,
                "event": event,
                "event_type": event_type,
                "event_type_label": get_event_type_label(event_type),
                "feedback_event": get_feedback_event(),
                "total_members": len(members_data),
            },
        )

    attendance = None
    if event:
        attendance = Attendance.objects.filter(war_event=event, member=member).first()

    pending_member_update = (
        MemberRequest.objects.filter(
            request_type=MemberRequest.RequestType.UPDATE,
            target_member=member,
            status=MemberRequest.Status.PENDING,
        )
        .order_by("-created_at")
        .first()
    )

    return render(
        request,
        "checkin_status.html",
        {
            "member": member,
            "event": event,
            "event_type": event_type,
            "event_type_label": get_event_type_label(event_type),
            "feedback_event": get_feedback_event(),
            "attendance": attendance,
            "status_choices": Attendance.Status.choices,
            "status_labels": dict(Attendance.Status.choices),
            "member_update_form": MemberUpdateRequestForm(member=member),
            "pending_member_update": pending_member_update,
        },
    )


@require_POST
def select_member_view(request, event_type=WarEvent.EventType.WAR):
    """
    POST /checkin/<event_type>/select-member/
    Validate member_id và set cookie.
    """
    event_type = normalize_event_type(event_type)
    member_id = request.POST.get("member_id", "").strip()

    if not member_id:
        messages.error(request, "Vui lòng chọn nhân vật từ danh sách.")
        return redirect("checkin_type", event_type=event_type)

    try:
        member = Member.objects.get(id=int(member_id), active=True)
    except (Member.DoesNotExist, ValueError, TypeError):
        messages.error(request, "Nhân vật không hợp lệ hoặc không còn trong bang.")
        return redirect("checkin_type", event_type=event_type)

    response = redirect("checkin_type", event_type=event_type)
    response.set_cookie(
        MEMBER_COOKIE_KEY,
        str(member.id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
        secure=not settings.DEBUG,
    )
    return response


@require_POST
@ratelimit(key="ip", rate="30/m", method="POST", block=False)
def submit_attendance_view(request, event_type=WarEvent.EventType.WAR):
    """
    POST /checkin/<event_type>/submit/
    Tạo hoặc cập nhật Attendance cho current event theo loại hoạt động.
    Rate limit 30/phút/IP: đủ rộng cho cả nhà chung mạng, chặn được script spam.
    """
    event_type = normalize_event_type(event_type)
    if getattr(request, "limited", False):
        messages.error(request, RATE_LIMIT_MESSAGE)
        return redirect("checkin_type", event_type=event_type)
    member = get_member_from_cookie(request)
    if not member:
        messages.error(request, "Vui lòng chọn nhân vật trước.")
        return redirect("checkin_type", event_type=event_type)

    event = get_current_event(event_type)
    if not event:
        messages.error(request, f"Hiện không có sự kiện {get_event_type_label(event_type)} nào đang mở.")
        return redirect("checkin_type", event_type=event_type)

    # Khóa sổ: check phía SERVER là lớp luật (ẩn nút phía client chỉ là lớp UX —
    # người mở sẵn form từ trước giờ khóa vẫn bấm gửi được nếu không chặn ở đây).
    if event.checkin_locked:
        lock_at = timezone.localtime(event.checkin_lock_at).strftime("%H:%M %d/%m")
        messages.error(
            request,
            f"Đã chốt sổ báo danh lúc {lock_at}. Cần thay đổi trạng thái, vui lòng liên hệ leader.",
        )
        return redirect("checkin_type", event_type=event_type)

    status = request.POST.get("status", "").strip()
    valid_statuses = [choice[0] for choice in Attendance.Status.choices]
    if status not in valid_statuses:
        messages.error(request, "Trạng thái không hợp lệ.")
        return redirect("checkin_type", event_type=event_type)

    device_id, _device_created = get_or_create_device_id(request)
    status_labels = dict(Attendance.Status.choices)

    try:
        attendance = Attendance.objects.get(war_event=event, member=member)
        changed = create_audit_log(
            attendance=attendance,
            new_status=status,
            device_id=device_id,
            actor_type=AttendanceAuditLog.ActorType.MEMBER,
        )

        if changed or attendance.note:
            attendance.status = status
            attendance.note = ""
            attendance.device_id = device_id
            if status == Attendance.Status.ABSENT:
                attendance.battle_team = ""
                attendance.battle_position = None
                attendance.strategy_note = ""
            attendance.save()

    except Attendance.DoesNotExist:
        Attendance.objects.create(
            war_event=event,
            member=member,
            status=status,
            note="",
            device_id=device_id,
            source=Attendance.Source.WEB,
        )

    messages.success(request, f"Đã ghi nhận: {member.display_name} – {status_labels[status]}")
    response = redirect("checkin_type", event_type=event_type)
    set_device_cookie(response, device_id)
    return response


@require_POST
@ratelimit(key="ip", rate="10/h", method="POST", block=False)
def request_member_update_view(request, event_type=WarEvent.EventType.WAR):
    """
    Tạo yêu cầu chỉnh thông tin cho nhân vật đang được chọn trong cookie.

    Member hiện tại không bị sửa trực tiếp. Leader phải duyệt request.
    """
    event_type = normalize_event_type(event_type)
    if getattr(request, "limited", False):
        messages.error(request, RATE_LIMIT_MESSAGE)
        return redirect("checkin_type", event_type=event_type)
    member = get_member_from_cookie(request)
    if not member:
        messages.error(request, "Vui lòng chọn nhân vật trước.")
        return redirect("checkin_type", event_type=event_type)

    form = MemberUpdateRequestForm(request.POST, member=member)
    if form.is_valid():
        member_request = form.save()
        messages.success(
            request,
            (
                "Đã gửi yêu cầu thay đổi thông tin. "
                "Leader sẽ duyệt trước khi tên hoặc phái được cập nhật."
            ),
        )
    else:
        error_messages = []
        for errors in form.errors.values():
            error_messages.extend(str(error) for error in errors)
        messages.error(
            request,
            " ".join(error_messages) or "Không thể gửi yêu cầu thay đổi.",
        )

    return redirect("checkin_type", event_type=event_type)


@require_POST
def clear_member_view(request, event_type=WarEvent.EventType.WAR):
    """Xóa cookie member đã chọn."""
    event_type = normalize_event_type(event_type)
    response = redirect("checkin_type", event_type=event_type)
    response.delete_cookie(MEMBER_COOKIE_KEY)
    return response


@ratelimit(key="ip", rate="10/h", method="POST", block=False)
def member_request_view(request):
    """
    GET/POST /member-request/
    Form để gửi yêu cầu thêm thành viên mới.
    BR4: Không tự động tạo Member chính thức.
    BR5: Tạo MemberRequest pending, admin duyệt mới tạo Member.
    Rate limit 10/giờ/IP để chặn spam tạo request rác.
    """
    if request.method == "POST":
        if getattr(request, "limited", False):
            messages.error(request, RATE_LIMIT_MESSAGE)
            return redirect("member_request")
        form = MemberRequestForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "Yêu cầu đã được gửi! Leader sẽ xem xét và thêm bạn vào danh sách thành viên.",
            )
            return redirect("member_request_done")
    else:
        form = MemberRequestForm()

    return render(request, "member_request.html", {"form": form})


def member_request_done_view(request):
    """Trang xác nhận sau khi gửi yêu cầu."""
    return render(request, "member_request_done.html")


@ratelimit(key="ip", rate="20/h", method="POST", block=False)
def feedback_view(request):
    """
    GET/POST /feedback/
    Feedback text ẩn danh mềm cho event gần nhất đã đến giờ bang chiến.
    Một browser/device cookie chỉ có 1 feedback/event và có thể sửa lại.
    Rate limit 20/giờ/IP: cookie chống trùng có thể bị xoá để lách, nên chặn thêm ở tầng IP.
    """
    if request.method == "POST" and getattr(request, "limited", False):
        messages.error(request, RATE_LIMIT_MESSAGE)
        return redirect("feedback")
    event = get_feedback_event()
    member = get_member_from_cookie(request)

    if not event:
        return render(request, "feedback_form.html", {"event": None})

    device_id, _device_created = get_or_create_device_id(request)
    existing_feedback = get_existing_feedback_for_request(request, event, device_id)

    if request.method == "POST":
        content = (request.POST.get("content") or "").strip()

        if len(content) < 2:
            messages.error(request, "Vui lòng nhập feedback trước khi gửi.")
            response = redirect("feedback")
            set_device_cookie(response, device_id)
            return response

        if len(content) > 2000:
            content = content[:2000]

        selected_member_id = request.COOKIES.get(MEMBER_COOKIE_KEY, "")
        feedback, created = BattleFeedback.objects.update_or_create(
            war_event=event,
            device_id_hash=hash_identifier(device_id),
            defaults={
                "content": content,
                "member_id_hash": hash_identifier(selected_member_id),
                "ip_hash": hash_identifier(get_client_ip(request)),
                "user_agent_hash": hash_identifier(request.META.get("HTTP_USER_AGENT", "")),
            },
        )

        messages.success(
            request,
            "Đã gửi feedback. Bạn có thể quay lại trang này để sửa feedback nếu vẫn dùng cùng trình duyệt.",
        )
        response = redirect("feedback")
        set_device_cookie(response, device_id)
        return response

    response = render(
        request,
        "feedback_form.html",
        {
            "event": event,
            "member": member,
            "existing_feedback": existing_feedback,
            "feedback_start_at": get_event_feedback_start_at(event),
        },
    )
    set_device_cookie(response, device_id)
    return response


@login_required
@user_passes_test(is_staff_user)
def leader_admin_log_view(request):
    """
    GET /leader/admin-log/
    Nhật ký thao tác quản trị: ai sửa gì, giá trị trước/sau, từ thiết bị nào.

    Gộp 2 nguồn:
    - AdminActionLog (của web này): có giá trị cũ→mới + IP/trình duyệt/mã máy.
    - LogEntry (sẵn có của Django): bắt được cả thao tác ở màn hình admin mà
      web chưa bọc, nhưng chỉ ghi tên trường đổi, không có giá trị cũ.
    """
    from django.contrib.admin.models import LogEntry

    actor = request.GET.get("actor", "").strip()
    action = request.GET.get("action", "").strip()
    obj_type = request.GET.get("object_type", "").strip()

    logs = AdminActionLog.objects.select_related("actor")
    if actor:
        logs = logs.filter(actor_username=actor)
    if action:
        logs = logs.filter(action=action)
    if obj_type:
        logs = logs.filter(object_type=obj_type)
    logs = logs[:200]

    # Nhãn tiếng Việt cho tên trường, để leader đọc hiểu thay vì thấy tên cột DB.
    field_labels = {
        "display_name": "Tên nhân vật",
        "class_name": "Phái",
        "class_variant": "Hệ/phân nhánh",
        "active": "Đang hoạt động",
        "note": "Ghi chú",
        "status": "Trạng thái",
        "title": "Tiêu đề",
        "event_date": "Ngày diễn ra",
        "is_current": "Event hiện tại",
        "battle_start_at": "Giờ đánh",
        "deadline_at": "Hạn báo danh",
        "battle_team": "Team",
        "battle_position": "Vị trí",
        "strategy_note": "Ghi chú chiến thuật",
    }
    rows = []
    for log in logs:
        pretty = []
        for field, pair in (log.changes or {}).items():
            old_v, new_v = (pair + [None, None])[:2] if isinstance(pair, list) else (None, pair)
            pretty.append(
                {
                    "label": field_labels.get(field, field),
                    "old": "—" if old_v in (None, "") else old_v,
                    "new": "—" if new_v in (None, "") else new_v,
                }
            )
        rows.append({"log": log, "changes": pretty})

    django_logs = (
        LogEntry.objects.select_related("user", "content_type").order_by("-action_time")[:50]
    )

    actors = (
        AdminActionLog.objects.exclude(actor_username="")
        .values_list("actor_username", flat=True)
        .distinct()
        .order_by("actor_username")
    )
    object_types = (
        AdminActionLog.objects.exclude(object_type="")
        .values_list("object_type", flat=True)
        .distinct()
        .order_by("object_type")
    )
    pending_requests_count = MemberRequest.objects.filter(
        status=MemberRequest.Status.PENDING
    ).count()

    return render(
        request,
        "leader_admin_log.html",
        {
            "rows": rows,
            "django_logs": django_logs,
            "actors": actors,
            "object_types": object_types,
            "filter_actor": actor,
            "filter_action": action,
            "filter_object_type": obj_type,
            "action_choices": AdminActionLog.Action.choices,
            "pending_requests_count": pending_requests_count,
        },
    )


@login_required
@user_passes_test(lambda u: u.is_staff)
def leader_attendance_history_view(request):
    """
    GET /leader/attendance-history/
    Ma trận chuyên cần: hàng = member, cột = 10 trận war gần nhất (mới nhất trái).
    3 màu ô: tham gia / bấm vắng / im lặng — đọc được pattern "vắng liên tiếp"
    mà con số tổng giấu mất.
    """
    events = stats.completed_war_events(limit=stats.DEFAULT_WINDOW)
    rows = stats.build_participation(events)
    ranked, newcomers = stats.rank_rows(rows)
    pending_requests_count = MemberRequest.objects.filter(
        status=MemberRequest.Status.PENDING
    ).count()
    return render(
        request,
        "leader_attendance_history.html",
        {
            "events": events,
            "ranked": ranked,
            "newcomers": newcomers,
            "window": stats.DEFAULT_WINDOW,
            "min_ranked": stats.MIN_RANKED_EVENTS,
            "pending_requests_count": pending_requests_count,
        },
    )


def public_leaderboard_view(request):
    """
    GET /public/leaderboard/
    BXH chuyên cần công khai. Chỉ tính trận WAR đã diễn ra xong.
    Xếp theo: số trận tham gia DESC -> tỷ lệ DESC (để 3/3 không đè 9/10).
    Member chưa đủ MIN_RANKED_EVENTS trận trong mẫu số -> khu "Thành viên mới",
    không đánh số hạng.
    """
    events = stats.completed_war_events(limit=stats.DEFAULT_WINDOW)
    rows = stats.build_participation(events)
    ranked, newcomers = stats.rank_rows(rows)
    return render(
        request,
        "public_leaderboard.html",
        {
            "ranked": ranked,
            "newcomers": newcomers,
            "events_count": len(events),
            "window": stats.DEFAULT_WINDOW,
            "min_ranked": stats.MIN_RANKED_EVENTS,
        },
    )


def public_result_live_view(request, event_type=WarEvent.EventType.WAR):
    """
    GET /public/result/<event_type>/live/
    Endpoint siêu mỏng cho polling (1 query aggregate):
    trả "phiên bản" dữ liệu — client so sánh, khác thì mới reload cả trang.
    """
    event_type = normalize_event_type(event_type)
    event = get_current_event(event_type)
    if not event:
        return JsonResponse({"v": "none"})
    agg = Attendance.objects.filter(war_event=event).aggregate(
        n=Count("id"), last=Max("updated_at")
    )
    version = f"{event.id}:{agg['n']}:{agg['last'].isoformat() if agg['last'] else 0}"
    return JsonResponse({"v": version})


@csrf_exempt
@require_POST
@ratelimit(key="ip", rate="30/h", method="POST", block=True)
def internal_daily_ops_view(request):
    """
    POST /internal/daily-ops/  (Authorization: Bearer <OPS_TOKEN>)
    Bộ kích hoạt việc định kỳ, GitHub Actions gọi mỗi sáng — thay cho scheduled
    task PythonAnywhere (free tier mới không còn). Idempotent: gọi lại vô hại.

    csrf_exempt vì đây là machine-to-machine, xác thực bằng bearer token
    (CSRF bảo vệ session cookie, không áp dụng cho kiểu gọi này).
    Token so sánh constant-time (hmac.compare_digest) chống dò theo thời gian.
    Token nằm trong HEADER, không trong URL — để không lọt vào access log.
    """
    expected = getattr(settings, "OPS_TOKEN", "")
    if not expected:
        return JsonResponse({"ok": False, "error": "endpoint disabled"}, status=403)
    auth = request.headers.get("Authorization", "")
    provided = auth[7:] if auth.startswith("Bearer ") else ""
    if not provided or not hmac.compare_digest(provided, expected):
        return JsonResponse({"ok": False, "error": "forbidden"}, status=403)
    return JsonResponse(ops.run_daily_ops())


def public_notify_data_view(request):
    """
    GET /public/notify-data/
    JSON tối giản cho bộ nhắc Discord chạy ngoài (GitHub Actions).
    Chỉ chứa dữ liệu vốn đã công khai trên trang kết quả — không lộ gì mới.
    """
    event = get_current_event(WarEvent.EventType.WAR)
    if not event:
        return JsonResponse({"has_event": False})
    joined = Attendance.objects.filter(
        war_event=event, status=Attendance.Status.JOINED
    ).count()
    deadline = None
    if event.deadline_at:
        d = timezone.localtime(event.deadline_at)
        vn_day = ["thứ 2", "thứ 3", "thứ 4", "thứ 5", "thứ 6", "thứ 7", "Chủ nhật"][d.weekday()]
        deadline = f"{d.strftime('%H:%M')} {vn_day}"
    return JsonResponse(
        {
            "has_event": True,
            "title": event.title,
            "joined": joined,
            "capacity": getattr(settings, "WAR_SLOT_CAPACITY", 60),
            "deadline": deadline,
        }
    )


def public_result_home_view(request):
    """GET /public/result/ – trang chọn kết quả Bang chiến hoặc Scrim."""
    war_event = get_current_event(WarEvent.EventType.WAR)
    scrim_event = get_current_event(WarEvent.EventType.SCRIM)
    return render(
        request,
        "public_result_home.html",
        {
            "war_event": war_event,
            "scrim_event": scrim_event,
            "feedback_event": get_feedback_event(),
        },
    )


def public_result_view(request, event_type=WarEvent.EventType.WAR):
    """
    GET /public/result/<event_type>/
    - Bang chiến: điểm danh + squad read-only.
    - Scrim: chỉ danh sách Tham gia / Không tham gia / Chưa điểm danh.
    """
    event_type = normalize_event_type(event_type)
    event = get_current_event(event_type)

    if not event:
        return render(
            request,
            "public_result.html",
            {
                "event": None,
                "event_type": event_type,
                "event_type_label": get_event_type_label(event_type),
                "is_war_event": event_type == WarEvent.EventType.WAR,
                "feedback_event": get_feedback_event(),
            },
        )

    all_members = Member.objects.filter(active=True).order_by("display_name")
    attendances = Attendance.objects.filter(war_event=event).select_related("member")
    attendance_map = {a.member_id: a for a in attendances}

    groups = {"joined": [], "absent": [], "no_response": []}

    for member in all_members:
        att = attendance_map.get(member.id)
        member_info = {
            "display_name": member.display_name,
            "class_name": member.class_name,
            "class_variant": member.class_variant,
            "class_label": member.class_label,
            "class_slug": member.class_slug,
            "variant_icon": member.variant_icon,
        }
        if att and att.status in groups:
            groups[att.status].append(member_info)
        else:
            groups["no_response"].append(member_info)

    counts = {k: len(v) for k, v in groups.items()}
    counts["total"] = all_members.count()

    boards = None
    if event_type == WarEvent.EventType.WAR:
        boards, _ = build_party_boards(event)

    return render(
        request,
        "public_result.html",
        {
            "event": event,
            "event_type": event_type,
            "event_type_label": get_event_type_label(event_type),
            "is_war_event": event_type == WarEvent.EventType.WAR,
            "groups": groups,
            "counts": counts,
            "boards": boards,
            "feedback_event": get_feedback_event(),
            "team_notes": get_team_notes(event) if event_type == WarEvent.EventType.WAR else {},
        },
    )


# ─────────────────────────────────────────────
# Leader / Admin Views (login required + staff)
# ─────────────────────────────────────────────


@login_required
@user_passes_test(is_staff_user)
def leader_dashboard_view(request, event_type=WarEvent.EventType.WAR):
    """
    GET /leader/dashboard/
    Dashboard cho leader: xem tổng quan, filter, search, sửa inline.
    """
    event_type = normalize_event_type(event_type)
    event = get_current_event(event_type)
    all_active_members = Member.objects.filter(active=True)
    total_active = all_active_members.count()
    recent_map = stats.dashboard_recent_map()  # member_id -> {"joined","denom"} 5 trận war gần

    if not event:
        return render(
            request,
            "leader_dashboard.html",
            {"event": None, "total_active": total_active, "event_type": event_type, "event_type_label": get_event_type_label(event_type)},
        )

    # Tính summary counts từ tất cả active members
    counts, attendance_map = build_attendance_summary(event)

    # Filter parameters từ GET
    status_filter = request.GET.get("status", "")
    class_filter = request.GET.get("class_name", "")
    search_q = request.GET.get("q", "").strip()

    # Build member queryset có filter
    members_qs = all_active_members
    if class_filter:
        members_qs = members_qs.filter(class_name=class_filter)
    if search_q:
        normalized_q = normalize_search_name(search_q)
        members_qs = members_qs.filter(
            Q(display_name__icontains=search_q) | Q(search_name__icontains=normalized_q)
        )

    # Build rows kết hợp member + attendance
    rows = []
    for member in members_qs.order_by("class_name", "display_name"):
        att = attendance_map.get(member.id)
        att_status = att.status if att else "no_response"

        # Apply status filter (bao gồm no_response)
        if status_filter and att_status != status_filter:
            continue

        rows.append(
            {
                "member": member,
                "attendance": att,
                "status": att_status,
                "recent": recent_map.get(member.id),  # {"joined","denom"} 5 trận war gần
            }
        )

    # Giá trị unique cho filter dropdowns
    class_names = (
        Member.objects.filter(active=True)
        .exclude(class_name="")
        .values_list("class_name", flat=True)
        .distinct()
        .order_by("class_name")
    )
    pending_requests_count = MemberRequest.objects.filter(
        status=MemberRequest.Status.PENDING
    ).count()

    return render(
        request,
        "leader_dashboard.html",
        {
            "event": event,
            "event_type": event_type,
            "event_type_label": get_event_type_label(event_type),
            "rows": rows,
            "counts": counts,
            "status_choices": Attendance.Status.choices,
            "status_labels": dict(Attendance.Status.choices),
            # Filters
            "class_names": class_names,
            "filter_status": status_filter,
            "filter_class": class_filter,
            "search_q": search_q,
            # Sidebar info
            "pending_requests_count": pending_requests_count,
            "all_events": WarEvent.objects.filter(event_type=event_type).order_by("-event_date")[:10],
        },
    )


@login_required
@user_passes_test(is_staff_user)
@require_POST
def leader_update_attendance_view(request, pk):
    """
    POST /leader/attendance/<pk>/update/
    Admin cập nhật attendance đã có.
    BR8: Tạo audit log với actor_type=admin.
    BR12: Leader có thể sửa nhanh.
    Returns JSON.
    """
    attendance = get_object_or_404(Attendance, pk=pk)

    new_status = request.POST.get("status", "").strip()

    valid_statuses = [choice[0] for choice in Attendance.Status.choices]
    if new_status not in valid_statuses:
        return JsonResponse({"success": False, "error": "Trạng thái không hợp lệ."}, status=400)

    # Tạo audit log nếu có thay đổi (BR8: actor_type=admin)
    changed = create_audit_log(
        attendance=attendance,
        new_status=new_status,
        device_id="admin",
        actor_type=AttendanceAuditLog.ActorType.ADMIN,
    )

    if changed or attendance.note:
        attendance.status = new_status
        attendance.note = ""
        attendance.source = Attendance.Source.ADMIN
        if new_status == Attendance.Status.ABSENT:
            attendance.battle_team = ""
            attendance.battle_position = None
            attendance.strategy_note = ""
        attendance.save()

    status_labels = dict(Attendance.Status.choices)
    return JsonResponse(
        {
            "success": True,
            "attendance_id": attendance.id,
            "status": attendance.status,
            "status_label": status_labels[attendance.status],
            "updated_at": timezone.localtime(attendance.updated_at).strftime("%H:%M %d/%m"),
        }
    )


@login_required
@user_passes_test(is_staff_user)
@require_POST
def leader_set_attendance_view(request):
    """
    POST /leader/attendance/set/
    Admin tạo hoặc cập nhật attendance cho member chưa báo danh.
    Dùng cho rows 'no_response' trong dashboard.
    BR8: audit log actor_type=admin.
    Returns JSON.
    """
    event_type = normalize_event_type(request.POST.get("event_type", WarEvent.EventType.WAR))
    event = get_current_event(event_type)
    if not event:
        return JsonResponse({"success": False, "error": "Không có event hiện tại."}, status=400)

    member_id = request.POST.get("member_id", "").strip()
    new_status = request.POST.get("status", "").strip()

    valid_statuses = [choice[0] for choice in Attendance.Status.choices]
    if new_status not in valid_statuses:
        return JsonResponse({"success": False, "error": "Trạng thái không hợp lệ."}, status=400)

    try:
        member = Member.objects.get(id=int(member_id), active=True)
    except (Member.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Member không hợp lệ."}, status=400)

    attendance, created = Attendance.objects.get_or_create(
        war_event=event,
        member=member,
        defaults={
            "status": new_status,
            "note": "",
            "source": Attendance.Source.ADMIN,
            "device_id": "admin",
        },
    )

    if not created:
        # Đã có attendance → update với audit log (BR8)
        changed = create_audit_log(
            attendance=attendance,
            new_status=new_status,
            device_id="admin",
            actor_type=AttendanceAuditLog.ActorType.ADMIN,
        )
        if changed or attendance.note:
            attendance.status = new_status
            attendance.note = ""
            attendance.source = Attendance.Source.ADMIN
            if new_status == Attendance.Status.ABSENT:
                attendance.battle_team = ""
                attendance.battle_position = None
                attendance.strategy_note = ""
            attendance.save()

    status_labels = dict(Attendance.Status.choices)
    return JsonResponse(
        {
            "success": True,
            "attendance_id": attendance.id,
            "status": attendance.status,
            "status_label": status_labels[attendance.status],
            "created": created,
            "updated_at": timezone.localtime(attendance.updated_at).strftime("%H:%M %d/%m"),
        }
    )


@login_required
@user_passes_test(is_staff_user)
def leader_party_board_view(request):
    """
    GET /leader/party-board/
    Giao diện kéo-thả xếp đội. Chỉ leader/staff được chỉnh.
    Vị trí đội hình lưu theo Attendance nên có thể thay đổi từng event/tuần.
    """
    event = get_current_event(WarEvent.EventType.WAR)
    if not event:
        messages.error(request, "Không có event bang chiến hiện tại để xếp đội.")
        return redirect("leader_dashboard_type", event_type=WarEvent.EventType.WAR)

    boards, unassigned = build_party_boards(event)

    return render(
        request,
        "leader_party_board.html",
        {
            "event": event,
            "boards": boards,
            "party_teams": PARTY_TEAMS,
            "unassigned": unassigned,
            "team_notes": get_team_notes(event),
        },
    )


@login_required
@user_passes_test(is_staff_user)
@require_POST
def leader_party_move_view(request):
    """
    POST /leader/party-board/move/
    Lưu drag/drop vị trí thành viên vào Attendance của event hiện tại.
    Nếu thả vào ô đã có người, hệ thống swap nếu người kéo có vị trí cũ,
    hoặc đẩy người cũ về unassigned.
    """
    event = get_current_event(WarEvent.EventType.WAR)
    if not event:
        return JsonResponse({"success": False, "error": "Không có event bang chiến hiện tại."}, status=400)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "Payload không hợp lệ."}, status=400)

    member_id = payload.get("member_id")
    target_team = payload.get("target_team", "")
    target_position = payload.get("target_position")

    try:
        member = Member.objects.get(id=int(member_id), active=True)
    except (Member.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Member không hợp lệ."}, status=400)

    try:
        attendance = Attendance.objects.get(war_event=event, member=member, status=Attendance.Status.JOINED)
    except Attendance.DoesNotExist:
        return JsonResponse({"success": False, "error": "Chỉ xếp được người đã báo Tham gia."}, status=400)

    old_team = attendance.battle_team
    old_position = attendance.battle_position

    if target_team == "unassigned" or target_team == "":
        attendance.battle_team = ""
        attendance.battle_position = None
        attendance.save(update_fields=["battle_team", "battle_position", "updated_at"])
        return JsonResponse({"success": True, "message": "Đã đưa về danh sách chưa xếp."})

    if target_team not in PARTY_TEAMS:
        return JsonResponse({"success": False, "error": "Team không hợp lệ."}, status=400)

    try:
        target_position = int(target_position)
    except (ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Vị trí không hợp lệ."}, status=400)

    capacity = PARTY_TEAMS[target_team]["capacity"]
    if not (1 <= target_position <= capacity):
        return JsonResponse({"success": False, "error": "Vị trí vượt quá sức chứa team."}, status=400)

    # Transaction + row lock: hai leader kéo thả cùng lúc không thể tạo 2 người cùng 1 ô.
    with transaction.atomic():
        occupant = (
            Attendance.objects.select_for_update()
            .filter(
                war_event=event,
                status=Attendance.Status.JOINED,
                battle_team=target_team,
                battle_position=target_position,
            )
            .exclude(member_id=member.id)
            .select_related("member")
            .first()
        )

        if occupant:
            if old_team in PARTY_TEAMS and old_position:
                occupant.battle_team = old_team
                occupant.battle_position = old_position
            else:
                occupant.battle_team = ""
                occupant.battle_position = None
            occupant.save(update_fields=["battle_team", "battle_position", "updated_at"])

        attendance.battle_team = target_team
        attendance.battle_position = target_position
        attendance.save(update_fields=["battle_team", "battle_position", "updated_at"])

    return JsonResponse({"success": True, "message": "Đã lưu vị trí đội hình."})


@login_required
@user_passes_test(is_staff_user)
@require_POST
def leader_party_note_view(request):
    """
    POST /leader/party-board/note/
    Leader cập nhật ghi chú skill/chiến thuật cá nhân theo Attendance của event hiện tại.
    """
    event = get_current_event(WarEvent.EventType.WAR)
    if not event:
        return JsonResponse({"success": False, "error": "Không có event bang chiến hiện tại."}, status=400)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "Payload không hợp lệ."}, status=400)

    member_id = payload.get("member_id")
    strategy_note = (payload.get("strategy_note") or "").strip()[:120]

    try:
        attendance = Attendance.objects.select_related("member").get(
            war_event=event, member_id=int(member_id), status=Attendance.Status.JOINED
        )
    except (Attendance.DoesNotExist, ValueError, TypeError):
        return JsonResponse({"success": False, "error": "Member chưa báo Tham gia."}, status=400)

    attendance.strategy_note = strategy_note
    attendance.source = Attendance.Source.ADMIN
    attendance.save(update_fields=["strategy_note", "source", "updated_at"])

    return JsonResponse({
        "success": True,
        "member_id": attendance.member_id,
        "strategy_note": strategy_note,
        "message": "Đã lưu ghi chú cá nhân.",
    })


@login_required
@user_passes_test(is_staff_user)
@require_POST
def leader_party_team_note_view(request):
    """
    POST /leader/party-board/team-note/
    Leader cập nhật ghi chú chiến thuật chung cho từng team trong event hiện tại.
    """
    event = get_current_event(WarEvent.EventType.WAR)
    if not event:
        return JsonResponse({"success": False, "error": "Không có event bang chiến hiện tại."}, status=400)

    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return JsonResponse({"success": False, "error": "Payload không hợp lệ."}, status=400)

    team_key = payload.get("team_key", "")
    note = (payload.get("note") or "").strip()[:800]

    if team_key not in PARTY_TEAMS:
        return JsonResponse({"success": False, "error": "Team không hợp lệ."}, status=400)

    team_notes = event.team_notes or {}
    team_notes[team_key] = note
    event.team_notes = team_notes
    event.save(update_fields=["team_notes", "updated_at"])

    return JsonResponse({
        "success": True,
        "team_key": team_key,
        "note": note,
        "message": "Đã lưu ghi chú team.",
    })


@login_required
@user_passes_test(is_staff_user)
def leader_feedback_events_view(request):
    """
    GET /leader/feedback/
    Danh sách event và số lượng feedback. Leader chỉ xem nội dung ẩn danh mềm.
    """
    events = (
        WarEvent.objects.annotate(feedback_count=Count("feedbacks"))
        .filter(feedback_count__gt=0)
        .order_by("-event_date", "-id")
    )
    pending_requests_count = MemberRequest.objects.filter(
        status=MemberRequest.Status.PENDING
    ).count()
    return render(
        request,
        "leader_feedback_events.html",
        {
            "events": events,
            "pending_requests_count": pending_requests_count,
        },
    )


@login_required
@user_passes_test(is_staff_user)
def leader_feedback_detail_view(request, event_id):
    """
    GET /leader/feedback/<event_id>/
    Leader xem nội dung feedback theo event. Không hiển thị audit hash/member/device.
    """
    event = get_object_or_404(WarEvent, pk=event_id)
    feedbacks = event.feedbacks.all().order_by("-created_at")
    pending_requests_count = MemberRequest.objects.filter(
        status=MemberRequest.Status.PENDING
    ).count()
    return render(
        request,
        "leader_feedback_detail.html",
        {
            "event": event,
            "feedbacks": feedbacks,
            "pending_requests_count": pending_requests_count,
        },
    )


@login_required
@user_passes_test(is_staff_user)
def export_csv_view(request):
    """
    GET /leader/export-csv/
    Xuất CSV điểm danh của current event (bao gồm cả no_response).
    """
    event_type = normalize_event_type(request.GET.get("type", WarEvent.EventType.WAR))
    event = get_current_event(event_type)
    if not event:
        messages.error(request, "Không có event hiện tại để xuất.")
        return redirect("leader_dashboard_type", event_type=event_type)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"bangcheck_{event.event_date.strftime('%Y%m%d')}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    # BOM để Excel đọc UTF-8 đúng
    response.write("\ufeff")

    writer = csv.writer(response)
    writer.writerow(
        ["Tên nhân vật", "Phái", "Hệ/phân nhánh", "Team xếp", "Vị trí", "Trạng thái", "Ghi chú skill", "Cập nhật lúc"]
    )

    all_members = Member.objects.filter(active=True).order_by("display_name")
    attendances = Attendance.objects.filter(war_event=event).select_related("member")
    attendance_map = {a.member_id: a for a in attendances}
    status_labels = dict(Attendance.Status.choices)

    for member in all_members:
        att = attendance_map.get(member.id)
        writer.writerow(
            [
                member.display_name,
                member.class_name,
                member.class_variant,
                dict(Member.BattleTeam.choices).get(att.battle_team, "Chưa xếp") if att and att.battle_team else "Chưa xếp",
                att.battle_position or "" if att else "",
                status_labels.get(att.status, "") if att else "Chưa phản hồi",
                att.strategy_note if att else "",
                att.updated_at.strftime("%d/%m/%Y %H:%M") if att else "",
            ]
        )

    return response


@login_required
@user_passes_test(is_staff_user)
def copy_summary_view(request):
    """
    GET /leader/copy-summary/
    Trả về plain text summary để copy (dùng AJAX từ dashboard).
    """
    event_type = normalize_event_type(request.GET.get("type", WarEvent.EventType.WAR))
    event = get_current_event(event_type)
    if not event:
        return HttpResponse("Không có event hiện tại.", content_type="text/plain; charset=utf-8")

    all_members = Member.objects.filter(active=True).order_by("display_name")
    attendances = Attendance.objects.filter(war_event=event).select_related("member")
    attendance_map = {a.member_id: a for a in attendances}

    groups = {"joined": [], "absent": [], "no_response": []}
    for member in all_members:
        att = attendance_map.get(member.id)
        key = att.status if att and att.status in groups else "no_response"
        groups[key].append(member.display_name)

    lines = [
        f"=== {event.get_event_type_display().upper()} {event.event_date.strftime('%d/%m/%Y')} – {event.title} ===",
        f"Tổng active: {all_members.count()} | "
        f"Tham gia: {len(groups['joined'])} | "
        f"Vắng: {len(groups['absent'])} | "
        f"Chưa phản hồi: {len(groups['no_response'])}",
        "",
    ]

    icons = {
        "joined": "✅ THAM GIA",
        "absent": "❌ KHÔNG THAM GIA",
        "no_response": "⏳ CHƯA PHẢN HỒI",
    }

    for key, label in icons.items():
        if groups[key]:
            lines.append(f"{label} ({len(groups[key])}):")
            for name in groups[key]:
                lines.append(f"  - {name}")
            lines.append("")

    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


@login_required
@user_passes_test(is_staff_user)
def leader_events_view(request):
    """
    GET /leader/events/
    Danh sách WarEvent. Leader set current event từ đây.
    """
    event_type_filter = request.GET.get("type", "")
    events = WarEvent.objects.order_by("event_type", "-event_date", "-id")
    if event_type_filter in {choice[0] for choice in WarEvent.EventType.choices}:
        events = events.filter(event_type=event_type_filter)
    pending_requests_count = MemberRequest.objects.filter(
        status=MemberRequest.Status.PENDING
    ).count()
    return render(
        request,
        "leader_events.html",
        {
            "events": events,
            "status_choices": WarEvent.Status.choices,
            "event_type_choices": WarEvent.EventType.choices,
            "event_type_filter": event_type_filter,
            "pending_requests_count": pending_requests_count,
        },
    )


@login_required
@user_passes_test(is_staff_user)
@require_POST
def leader_set_current_event_view(request, pk):
    """
    POST /leader/events/<pk>/set-current/
    Set event là current và open. Các event khác is_current=False.
    """
    event = get_object_or_404(WarEvent, pk=pk)
    WarEvent.objects.filter(event_type=event.event_type).update(is_current=False)
    event.is_current = True
    event.status = WarEvent.Status.OPEN
    event.save()
    messages.success(request, f'Đã set "{event.title}" ({event.get_event_type_display()} {event.event_date}) làm event hiện tại.')
    return redirect("leader_events")


@login_required
@user_passes_test(is_staff_user)
def leader_member_requests_view(request):
    """Danh sách chung cho yêu cầu tạo mới và chỉnh thông tin."""
    status_filter = request.GET.get("status", "pending")
    type_filter = request.GET.get("type", "")

    requests_qs = (
        MemberRequest.objects.select_related("target_member", "reviewed_by")
        .order_by("-created_at")
    )
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)
    if type_filter in {
        MemberRequest.RequestType.ADD,
        MemberRequest.RequestType.UPDATE,
    }:
        requests_qs = requests_qs.filter(request_type=type_filter)
    else:
        type_filter = ""

    pending_count = MemberRequest.objects.filter(
        status=MemberRequest.Status.PENDING
    ).count()

    return render(
        request,
        "leader_member_requests.html",
        {
            "requests": requests_qs,
            "status_filter": status_filter,
            "type_filter": type_filter,
            "status_choices": MemberRequest.Status.choices,
            "request_type_choices": MemberRequest.RequestType.choices,
            "pending_requests_count": pending_count,
        },
    )


@login_required
@user_passes_test(is_staff_user)
@require_POST
def approve_member_request_view(request, pk):
    """Duyệt request và áp dụng thay đổi trong một transaction."""
    review_note = (request.POST.get("review_note") or "").strip()
    try:
        _member_request, _member, result_message = approve_member_request(
            pk,
            request.user,
            review_note=review_note,
        )
    except MemberRequest.DoesNotExist:
        messages.error(request, "Không tìm thấy yêu cầu.")
    except MemberRequestError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, result_message)

    return safe_next_redirect(request, "leader_member_requests")


@login_required
@user_passes_test(is_staff_user)
@require_POST
def reject_member_request_view(request, pk):
    """Từ chối request và lưu người/thời gian/ghi chú xử lý."""
    review_note = (request.POST.get("review_note") or "").strip()
    try:
        member_request = reject_member_request(
            pk,
            request.user,
            review_note=review_note,
        )
    except MemberRequest.DoesNotExist:
        messages.error(request, "Không tìm thấy yêu cầu.")
    except MemberRequestError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request,
            f"Đã từ chối yêu cầu của {member_request.requested_name}.",
        )

    return safe_next_redirect(request, "leader_member_requests")
