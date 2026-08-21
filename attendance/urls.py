"""
attendance/urls.py – URL routes cho bangcheck.
"""

from django.urls import path
from . import views

urlpatterns = [
    # ── Public / Member ──────────────────────────────
    path("checkin/", views.checkin_home_view, name="checkin"),
    # Legacy routes default to Bang chiến. Đặt trước dynamic route để không bị bắt nhầm event_type.
    path("checkin/select-member/", views.select_member_view, name="select_member"),
    path("checkin/submit/", views.submit_attendance_view, name="submit_attendance"),
    path("checkin/clear-member/", views.clear_member_view, name="clear_member"),
    path("checkin/<str:event_type>/select-member/", views.select_member_view, name="select_member_type"),
    path("checkin/<str:event_type>/submit/", views.submit_attendance_view, name="submit_attendance_type"),
    path("checkin/<str:event_type>/request-update/", views.request_member_update_view, name="request_member_update"),
    path("checkin/<str:event_type>/clear-member/", views.clear_member_view, name="clear_member_type"),
    path("checkin/<str:event_type>/", views.checkin_view, name="checkin_type"),
    path("feedback/", views.feedback_view, name="feedback"),

    # Member request
    path("member-request/", views.member_request_view, name="member_request"),
    path("member-request/done/", views.member_request_done_view, name="member_request_done"),

    # Public result (không cần login)
    path("public/result/", views.public_result_home_view, name="public_result"),
    path("public/result/<str:event_type>/live/", views.public_result_live_view, name="public_result_live"),
    path("public/result/<str:event_type>/", views.public_result_view, name="public_result_type"),
    path("public/leaderboard/", views.public_leaderboard_view, name="public_leaderboard"),
    path("public/notify-data/", views.public_notify_data_view, name="public_notify_data"),
    path("internal/daily-ops/", views.internal_daily_ops_view, name="internal_daily_ops"),

    # ── Leader Area (staff login required) ───────────
    path("leader/dashboard/", views.leader_dashboard_view, name="leader_dashboard"),
    path("leader/attendance-history/", views.leader_attendance_history_view, name="leader_attendance_history"),
    path("leader/admin-log/", views.leader_admin_log_view, name="leader_admin_log"),
    path("leader/dashboard/<str:event_type>/", views.leader_dashboard_view, name="leader_dashboard_type"),
    path("leader/attendance/<int:pk>/update/", views.leader_update_attendance_view, name="leader_update_attendance"),
    path("leader/attendance/set/", views.leader_set_attendance_view, name="leader_set_attendance"),
    path("leader/feedback/", views.leader_feedback_events_view, name="leader_feedback_events"),
    path("leader/feedback/<int:event_id>/", views.leader_feedback_detail_view, name="leader_feedback_detail"),
    path("leader/export-csv/", views.export_csv_view, name="export_csv"),
    path("leader/copy-summary/", views.copy_summary_view, name="copy_summary"),
    path("leader/party-board/", views.leader_party_board_view, name="leader_party_board"),
    path("leader/party-board/move/", views.leader_party_move_view, name="leader_party_move"),
    path("leader/party-board/note/", views.leader_party_note_view, name="leader_party_note"),
    path("leader/party-board/team-note/", views.leader_party_team_note_view, name="leader_party_team_note"),

    # Events management
    path("leader/events/", views.leader_events_view, name="leader_events"),
    path("leader/events/<int:pk>/set-current/", views.leader_set_current_event_view, name="leader_set_current_event"),

    # Member requests management
    path("leader/member-requests/", views.leader_member_requests_view, name="leader_member_requests"),
    path("leader/member-requests/<int:pk>/approve/", views.approve_member_request_view, name="approve_member_request"),
    path("leader/member-requests/<int:pk>/reject/", views.reject_member_request_view, name="reject_member_request"),
]
