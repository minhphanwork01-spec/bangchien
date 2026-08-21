"""
Thống kê chuyên cần.

Quy tắc đã chốt:
- Cửa sổ tính = N trận WAR gần nhất ĐÃ DIỄN RA XONG (trận chưa đánh không tính,
  để giữa tuần không ai bị tính "im lặng" oan cho trận sắp tới).
- Chỉ status JOINED được tính điểm; ABSENT (bấm Vắng) và NO_RESPONSE (im lặng)
  đều là không tham gia — nhưng hiển thị phân biệt để leader đọc được pattern.
- Mẫu số cá nhân hóa: member mới chỉ bị tính trên các trận tồn tại SAU khi họ
  vào bang (so theo created_at), tránh oan "0/10" cho người mới vào 2 tuần.
- BXH: cần tối thiểu MIN_RANKED_EVENTS trận trong mẫu số mới được xếp hạng.
  Xếp theo (số trận tham gia DESC, tỷ lệ DESC, tên) — số trận là khóa chính
  để 3/3 không đè 9/10.
"""
from django.utils import timezone

from .models import Attendance, Member, WarEvent

DEFAULT_WINDOW = 10
DASHBOARD_WINDOW = 5
MIN_RANKED_EVENTS = 3


def completed_war_events(limit=DEFAULT_WINDOW):
    """
    N trận war gần nhất đã diễn ra xong, MỚI NHẤT TRƯỚC.
    "Đã diễn ra xong" = giờ đánh trận (battle_start_at) đã qua; event không set
    giờ đánh thì rơi về hết ngày event_date.
    """
    now = timezone.localtime()
    today = now.date()
    events = (
        WarEvent.objects.filter(event_type=WarEvent.EventType.WAR)
        .filter(event_date__lte=today)
        .order_by("-event_date", "-id")
    )
    out = []
    for ev in events:
        if ev.battle_start_at is not None:
            started = ev.battle_start_at <= timezone.now()
        else:
            started = ev.event_date < today  # không set giờ: hết ngày mới tính xong
        if started:
            out.append(ev)
            if len(out) >= limit:
                break
    return out


def build_participation(events, members=None):
    """
    Tính chuyên cần cho từng member trên danh sách events (mới nhất trước).

    Trả về list dict, mỗi member gồm:
      member, cells (list state theo thứ tự events: joined/absent/no_response/before),
      joined (số trận tham gia), denom (mẫu số cá nhân hóa),
      pct (0-100, None nếu denom=0), is_new (denom < MIN_RANKED_EVENTS).

    "before" = trận diễn ra trước khi member vào bang — không tính vào mẫu số.
    """
    if members is None:
        members = Member.objects.filter(active=True).order_by("display_name")
    event_ids = [ev.id for ev in events]

    # Một query lấy toàn bộ attendance của cửa sổ, tra bằng dict — tránh N+1.
    att_map = {}
    if event_ids:
        for att in Attendance.objects.filter(war_event_id__in=event_ids).only(
            "war_event_id", "member_id", "status"
        ):
            att_map[(att.war_event_id, att.member_id)] = att.status

    rows = []
    for m in members:
        cells, joined, denom = [], 0, 0
        for ev in events:
            if m.created_at is not None and m.created_at > _event_moment(ev):
                cells.append("before")
                continue
            denom += 1
            status = att_map.get((ev.id, m.id))
            if status == Attendance.Status.JOINED:
                joined += 1
                cells.append("joined")
            elif status == Attendance.Status.ABSENT:
                cells.append("absent")
            else:
                cells.append("no_response")
        pct = round(joined * 100 / denom) if denom else None
        rows.append(
            {
                "member": m,
                "cells": cells,
                "joined": joined,
                "denom": denom,
                "pct": pct,
                "is_new": denom < MIN_RANKED_EVENTS,
            }
        )
    return rows


def _event_moment(ev):
    """Thời điểm đại diện của event để so với created_at của member."""
    if ev.battle_start_at is not None:
        return ev.battle_start_at
    tz = timezone.get_current_timezone()
    from datetime import datetime, time as dtime

    return timezone.make_aware(datetime.combine(ev.event_date, dtime(23, 59)), tz)


def rank_rows(rows):
    """
    Chia (ranked, newcomers) và xếp hạng ranked.
    Khóa sort: số trận tham gia DESC -> tỷ lệ DESC -> tên. Gắn row["rank"] 1-based.
    """
    ranked = [r for r in rows if not r["is_new"]]
    newcomers = [r for r in rows if r["is_new"]]
    ranked.sort(key=lambda r: (-r["joined"], -(r["pct"] or 0), r["member"].display_name))
    newcomers.sort(key=lambda r: (-r["joined"], r["member"].display_name))
    for i, r in enumerate(ranked, start=1):
        r["rank"] = i
    return ranked, newcomers


def dashboard_recent_map(window=DASHBOARD_WINDOW):
    """Map member_id -> "j/d" cho cột nhỏ trong bảng dashboard (5 trận gần nhất)."""
    events = completed_war_events(limit=window)
    rows = build_participation(events)
    return {r["member"].id: {"joined": r["joined"], "denom": r["denom"]} for r in rows}
