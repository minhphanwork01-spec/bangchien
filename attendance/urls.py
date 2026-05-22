"""
attendance/urls.py – URL routes cho bangcheck.
"""

from django.urls import path
from . import views

urlpatterns = [
    # ── Public / Member ──────────────────────────────
    path("checkin/", views.checkin_view, name="checkin"),
    path("checkin/select-member/", views.select_member_view, name="select_member"),
    path("checkin/submit/", views.submit_attendance_view, name="submit_attendance"),
    path("checkin/clear-member/", views.clear_member_view, name="clear_member"),

    # Member request
    path("member-request/", views.member_request_view, name="member_request"),
    path("member-request/done/", views.member_request_done_view, name="member_request_done"),

    # Public result (không cần login)
    path("public/result/", views.public_result_view, name="public_result"),

    # ── Leader Area (staff login required) ───────────
    path("leader/dashboard/", views.leader_dashboard_view, name="leader_dashboard"),
    path(
        "leader/attendance/<int:pk>/update/",
        views.leader_update_attendance_view,
        name="leader_update_attendance",
    ),
    path(
        "leader/attendance/set/",
        views.leader_set_attendance_view,
        name="leader_set_attendance",
    ),
    path("leader/export-csv/", views.export_csv_view, name="export_csv"),
    path("leader/copy-summary/", views.copy_summary_view, name="copy_summary"),
    path("leader/party-board/", views.leader_party_board_view, name="leader_party_board"),
    path("leader/party-board/move/", views.leader_party_move_view, name="leader_party_move"),
    path("leader/party-board/note/", views.leader_party_note_view, name="leader_party_note"),
    path("leader/party-board/team-note/", views.leader_party_team_note_view, name="leader_party_team_note"),

    # War Events management
    path("leader/events/", views.leader_events_view, name="leader_events"),
    path(
        "leader/events/<int:pk>/set-current/",
        views.leader_set_current_event_view,
        name="leader_set_current_event",
    ),

    # Member requests management
    path(
        "leader/member-requests/",
        views.leader_member_requests_view,
        name="leader_member_requests",
    ),
    path(
        "leader/member-requests/<int:pk>/approve/",
        views.approve_member_request_view,
        name="approve_member_request",
    ),
    path(
        "leader/member-requests/<int:pk>/reject/",
        views.reject_member_request_view,
        name="reject_member_request",
    ),
]
