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
import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import MemberRequestForm
from .models import Attendance, AttendanceAuditLog, Member, MemberRequest, WarEvent, normalize_search_name

# Cookie key để lưu member đã chọn
MEMBER_COOKIE_KEY = "selected_member_id"
# 30 ngày
COOKIE_MAX_AGE = 60 * 60 * 24 * 30

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


def get_current_event():
    """
    Lấy event hiện tại đang mở.
    Ưu tiên WarEvent.is_current=True, nếu không có thì fallback event open mới nhất.
    """
    event = WarEvent.objects.filter(is_current=True, status=WarEvent.Status.OPEN).first()
    if event:
        return event
    return WarEvent.objects.filter(status=WarEvent.Status.OPEN).order_by("-event_date").first()


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


def checkin_view(request):
    """
    GET /checkin/
    - Nếu chưa có member trong cookie: hiển thị màn hình chọn nhân vật.
    - Nếu đã có member hợp lệ: hiển thị form điểm danh.
    """
    member = get_member_from_cookie(request)
    event = get_current_event()

    if member is None:
        # Chưa chọn nhân vật → màn hình "Bạn là ai?"
        # Load tất cả active members thành JSON để JS filter client-side
        # BR2/BR3: Search chỉ để lọc hiển thị, submit dùng member_id
        members_qs = Member.objects.filter(active=True).order_by("display_name")
        members_data = [
            {
                "id": m.id,
                "display_name": m.display_name,
                "search_name": m.search_name,  # đã normalize (không dấu, lowercase)
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
                "members_json": json.dumps(members_data, ensure_ascii=False),
                "event": event,
                "total_members": len(members_data),
            },
        )

    # Đã có member → màn hình điểm danh
    attendance = None
    if event:
        attendance = Attendance.objects.filter(war_event=event, member=member).first()

    return render(
        request,
        "checkin_status.html",
        {
            "member": member,
            "event": event,
            "attendance": attendance,
            "status_choices": Attendance.Status.choices,
            "status_labels": dict(Attendance.Status.choices),
        },
    )


@require_POST
def select_member_view(request):
    """
    POST /checkin/select-member/
    Validate member_id và set cookie.
    BR1: Chỉ chấp nhận member_id hợp lệ từ DB, không lưu text input.
    """
    member_id = request.POST.get("member_id", "").strip()

    if not member_id:
        messages.error(request, "Vui lòng chọn nhân vật từ danh sách.")
        return redirect("checkin")

    try:
        member = Member.objects.get(id=int(member_id), active=True)
    except (Member.DoesNotExist, ValueError, TypeError):
        messages.error(request, "Nhân vật không hợp lệ hoặc không còn trong bang.")
        return redirect("checkin")

    response = redirect("checkin")
    response.set_cookie(
        MEMBER_COOKIE_KEY,
        str(member.id),
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )
    return response


@require_POST
def submit_attendance_view(request):
    """
    POST /checkin/submit/
    Tạo hoặc cập nhật Attendance cho current WarEvent.
    BR6: update_or_create đảm bảo 1 record/member/event.
    BR7: Tạo audit log khi thay đổi.
    """
    member = get_member_from_cookie(request)
    if not member:
        messages.error(request, "Vui lòng chọn nhân vật trước.")
        return redirect("checkin")

    event = get_current_event()
    if not event:
        messages.error(request, "Hiện không có sự kiện bang chiến nào đang mở.")
        return redirect("checkin")

    status = request.POST.get("status", "").strip()

    valid_statuses = [choice[0] for choice in Attendance.Status.choices]
    if status not in valid_statuses:
        messages.error(request, "Trạng thái không hợp lệ.")
        return redirect("checkin")

    # device_id = member_id từ cookie (không phải bảo mật, chỉ để track)
    device_id = request.COOKIES.get(MEMBER_COOKIE_KEY, "")
    status_labels = dict(Attendance.Status.choices)

    try:
        # Lấy attendance đã có
        attendance = Attendance.objects.get(war_event=event, member=member)

        # Kiểm tra thay đổi và tạo audit log (BR7)
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
        # Lần đầu báo danh cho event này
        attendance = Attendance.objects.create(
            war_event=event,
            member=member,
            status=status,
            note="",
            device_id=device_id,
            source=Attendance.Source.WEB,
        )

    messages.success(
        request,
        f"✅ Đã ghi nhận: {member.display_name} – {status_labels[status]}",
    )
    return redirect("checkin")


@require_POST
def clear_member_view(request):
    """
    POST /checkin/clear-member/
    Xóa cookie → member phải chọn lại từ danh sách (BR10).
    """
    response = redirect("checkin")
    response.delete_cookie(MEMBER_COOKIE_KEY)
    return response


def member_request_view(request):
    """
    GET/POST /member-request/
    Form để gửi yêu cầu thêm thành viên mới.
    BR4: Không tự động tạo Member chính thức.
    BR5: Tạo MemberRequest pending, admin duyệt mới tạo Member.
    """
    if request.method == "POST":
        form = MemberRequestForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                "✅ Yêu cầu đã được gửi! Leader sẽ xem xét và thêm bạn vào danh sách thành viên.",
            )
            return redirect("member_request_done")
    else:
        form = MemberRequestForm()

    return render(request, "member_request.html", {"form": form})


def member_request_done_view(request):
    """Trang xác nhận sau khi gửi yêu cầu."""
    return render(request, "member_request_done.html")


def public_result_view(request):
    """
    GET /public/result/
    Xem kết quả điểm danh + squad read-only. Không cần login.
    """
    event = get_current_event()

    if not event:
        return render(request, "public_result.html", {"event": None})

    all_members = Member.objects.filter(active=True).order_by("display_name")
    attendances = Attendance.objects.filter(war_event=event).select_related("member")
    attendance_map = {a.member_id: a for a in attendances}

    groups = {
        "joined": [],
        "absent": [],
        "no_response": [],
    }

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
    boards, _ = build_party_boards(event)

    return render(
        request,
        "public_result.html",
        {
            "event": event,
            "groups": groups,
            "counts": counts,
            "boards": boards,
            "team_notes": get_team_notes(event),
        },
    )


# ─────────────────────────────────────────────
# Leader / Admin Views (login required + staff)
# ─────────────────────────────────────────────


@login_required
@user_passes_test(is_staff_user)
def leader_dashboard_view(request):
    """
    GET /leader/dashboard/
    Dashboard cho leader: xem tổng quan, filter, search, sửa inline.
    """
    event = get_current_event()
    all_active_members = Member.objects.filter(active=True)
    total_active = all_active_members.count()

    if not event:
        return render(
            request,
            "leader_dashboard.html",
            {"event": None, "total_active": total_active},
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
            "all_events": WarEvent.objects.order_by("-event_date")[:10],
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
    event = get_current_event()
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
    event = get_current_event()
    if not event:
        messages.error(request, "Không có event hiện tại để xếp đội.")
        return redirect("leader_dashboard")

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
    event = get_current_event()
    if not event:
        return JsonResponse({"success": False, "error": "Không có event hiện tại."}, status=400)

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

    occupant = (
        Attendance.objects.filter(
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
    event = get_current_event()
    if not event:
        return JsonResponse({"success": False, "error": "Không có event hiện tại."}, status=400)

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
    event = get_current_event()
    if not event:
        return JsonResponse({"success": False, "error": "Không có event hiện tại."}, status=400)

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
def export_csv_view(request):
    """
    GET /leader/export-csv/
    Xuất CSV điểm danh của current event (bao gồm cả no_response).
    """
    event = get_current_event()
    if not event:
        messages.error(request, "Không có event hiện tại để xuất.")
        return redirect("leader_dashboard")

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
    event = get_current_event()
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
        f"=== BANG CHIẾN {event.event_date.strftime('%d/%m/%Y')} – {event.title} ===",
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
    events = WarEvent.objects.order_by("-event_date")
    pending_requests_count = MemberRequest.objects.filter(
        status=MemberRequest.Status.PENDING
    ).count()
    return render(
        request,
        "leader_events.html",
        {
            "events": events,
            "status_choices": WarEvent.Status.choices,
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
    WarEvent.objects.all().update(is_current=False)
    event.is_current = True
    event.status = WarEvent.Status.OPEN
    event.save()
    messages.success(request, f'✅ Đã set "{event.title}" ({event.event_date}) làm event hiện tại.')
    return redirect("leader_events")


@login_required
@user_passes_test(is_staff_user)
def leader_member_requests_view(request):
    """
    GET /leader/member-requests/
    Xem và xử lý yêu cầu thêm thành viên.
    """
    status_filter = request.GET.get("status", "pending")
    requests_qs = MemberRequest.objects.order_by("-created_at")
    if status_filter:
        requests_qs = requests_qs.filter(status=status_filter)

    pending_count = MemberRequest.objects.filter(status=MemberRequest.Status.PENDING).count()

    return render(
        request,
        "leader_member_requests.html",
        {
            "requests": requests_qs,
            "status_filter": status_filter,
            "status_choices": MemberRequest.Status.choices,
            "pending_requests_count": pending_count,
        },
    )


@login_required
@user_passes_test(is_staff_user)
@require_POST
def approve_member_request_view(request, pk):
    """
    POST /leader/member-requests/<pk>/approve/
    Duyệt yêu cầu: tạo Member mới từ MemberRequest.
    BR4: Chỉ admin mới tạo Member chính thức.
    """
    mr = get_object_or_404(MemberRequest, pk=pk, status=MemberRequest.Status.PENDING)

    member = Member.objects.create(
        display_name=mr.requested_name,
        class_name=mr.class_name,
        class_variant=mr.class_variant,
        note=mr.note,
        active=True,
    )

    mr.status = MemberRequest.Status.APPROVED
    mr.save()

    messages.success(
        request,
        f"✅ Đã duyệt và thêm {member.display_name} vào danh sách thành viên.",
    )
    return redirect("leader_member_requests")


@login_required
@user_passes_test(is_staff_user)
@require_POST
def reject_member_request_view(request, pk):
    """
    POST /leader/member-requests/<pk>/reject/
    Từ chối yêu cầu thêm thành viên.
    """
    mr = get_object_or_404(MemberRequest, pk=pk, status=MemberRequest.Status.PENDING)
    mr.status = MemberRequest.Status.REJECTED
    mr.save()
    messages.success(request, f"Đã từ chối yêu cầu của {mr.requested_name}.")
    return redirect("leader_member_requests")
