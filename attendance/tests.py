"""
Bộ test tối thiểu bảo vệ core business rules.
Chạy: python manage.py test attendance

Mục đích: mọi lần sửa code (kể cả code do AI sinh) chạy lệnh trên trước khi
deploy — pass hết nghĩa là không phá luồng cũ.
"""
from datetime import timedelta

from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models.deletion import ProtectedError
from django.test import Client, TestCase, override_settings
from django.utils import timezone

from . import stats
from .models import Attendance, Member, MemberRequest, WarEvent


def make_event(days_ago=0, current=True, deadline=None, battle=None, etype=WarEvent.EventType.WAR):
    d = timezone.localtime().date() - timedelta(days=days_ago)
    return WarEvent.objects.create(
        event_type=etype,
        title=f"Test {d}",
        event_date=d,
        is_current=current,
        status=WarEvent.Status.OPEN,
        deadline_at=deadline,
        battle_start_at=battle,
    )


def make_member(name, days_ago=365):
    m = Member.objects.create(display_name=name, class_name="Huyết Hà", active=True)
    # created_at auto_now_add — chỉnh lùi để test mẫu số cá nhân hóa
    Member.objects.filter(pk=m.pk).update(created_at=timezone.now() - timedelta(days=days_ago))
    m.refresh_from_db()
    return m


class CheckinFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.member = make_member("Kiếm Khách A")
        self.event = make_event()
        self.client = Client()
        self.client.post("/checkin/war/select-member/", {"member_id": self.member.id})

    def test_submit_creates_attendance(self):
        r = self.client.post("/checkin/war/submit/", {"status": "joined"}, follow=True)
        self.assertEqual(r.status_code, 200)
        self.assertTrue(
            Attendance.objects.filter(
                war_event=self.event, member=self.member, status="joined"
            ).exists()
        )

    def test_submit_blocked_after_deadline(self):
        """Khóa sổ: quá deadline_at là server từ chối, member không đổi được trạng thái."""
        self.event.deadline_at = timezone.now() - timedelta(minutes=5)
        self.event.save()
        r = self.client.post("/checkin/war/submit/", {"status": "joined"}, follow=True)
        self.assertContains(r, "chốt sổ")
        self.assertFalse(Attendance.objects.filter(war_event=self.event).exists())

    def test_submit_blocked_after_battle_start_fallback(self):
        """Không set deadline thì rơi về giờ đánh trận."""
        self.event.battle_start_at = timezone.now() - timedelta(minutes=5)
        self.event.save()
        r = self.client.post("/checkin/war/submit/", {"status": "joined"}, follow=True)
        self.assertContains(r, "chốt sổ")

    def test_leader_can_edit_after_lock(self):
        """Van xả: dashboard leader KHÔNG bị khóa sổ chặn."""
        Attendance.objects.create(war_event=self.event, member=self.member, status="absent")
        self.event.deadline_at = timezone.now() - timedelta(minutes=5)
        self.event.save()
        leader = User.objects.create_user("lead", password="x", is_staff=True)
        c = Client()
        c.force_login(leader)
        att = Attendance.objects.get(war_event=self.event, member=self.member)
        r = c.post(
            f"/leader/attendance/{att.pk}/update/", {"status": "joined"}, follow=True
        )
        att.refresh_from_db()
        self.assertEqual(att.status, "joined")


class MemberRequestTests(TestCase):
    def setUp(self):
        cache.clear()
        self.leader = User.objects.create_user("lead", password="x", is_staff=True)
        self.client = Client()
        self.client.force_login(self.leader)

    def test_approve_add_creates_member(self):
        mr = MemberRequest.objects.create(
            request_type="add", requested_name="Tân Thủ", class_name="Thiết Y", class_variant="Ngự"
        )
        self.client.post(f"/leader/member-requests/{mr.pk}/approve/")
        self.assertTrue(Member.objects.filter(display_name="Tân Thủ").exists())

    def test_open_redirect_blocked(self):
        mr = MemberRequest.objects.create(
            request_type="add", requested_name="X", class_name="Huyết Hà"
        )
        r = self.client.post(
            f"/leader/member-requests/{mr.pk}/approve/", {"next": "https://evil.com/x"}
        )
        self.assertNotIn("evil.com", r.headers.get("Location", ""))


class MemberProtectTests(TestCase):
    def test_delete_member_with_history_blocked(self):
        """PROTECT: xoá member còn lịch sử điểm danh phải bị chặn — dữ liệu chuyên cần bất khả xâm."""
        m = make_member("Cựu Binh")
        ev = make_event()
        Attendance.objects.create(war_event=ev, member=m, status="joined")
        with self.assertRaises(ProtectedError):
            m.delete()
        # Quy trình đúng: rời bang = tắt active, lịch sử còn nguyên
        m.active = False
        m.save()
        self.assertTrue(Attendance.objects.filter(member=m).exists())


class StatsTests(TestCase):
    """Luật chuyên cần đã chốt — đây là hợp đồng, sửa luật phải sửa test có chủ đích."""

    def _completed_event(self, days_ago):
        return make_event(days_ago=days_ago, current=False)

    def test_only_completed_war_events_in_window(self):
        past = self._completed_event(3)
        make_event(days_ago=0, current=True, battle=timezone.now() + timedelta(hours=5))  # chưa đánh
        make_event(days_ago=2, current=False, etype=WarEvent.EventType.SCRIM)  # scrim
        events = stats.completed_war_events()
        self.assertEqual([e.id for e in events], [past.id])

    def test_personalized_denominator_and_scoring(self):
        """Case của user: 10 trận, 4 joined + 3 absent + 3 im lặng = 4/10 = 40%.
        Member mới vào giữa chừng chỉ bị tính các trận sau khi vào bang."""
        events = [self._completed_event(days_ago=i + 1) for i in range(10)]  # mới nhất trước
        vet = make_member("Lão Làng", days_ago=365)
        rookie = make_member("Tân Binh", days_ago=2)  # chỉ tồn tại qua 1-2 trận gần nhất
        for i, ev in enumerate(events):
            if i < 4:
                Attendance.objects.create(war_event=ev, member=vet, status="joined")
            elif i < 7:
                Attendance.objects.create(war_event=ev, member=vet, status="absent")
            # 3 trận cuối: im lặng (không có bản ghi)
        rows = {r["member"].id: r for r in stats.build_participation(stats.completed_war_events())}
        v = rows[vet.id]
        self.assertEqual((v["joined"], v["denom"], v["pct"]), (4, 10, 40))
        r = rows[rookie.id]
        self.assertLess(r["denom"], 3)
        self.assertTrue(r["is_new"])

    def test_ranking_count_beats_ratio(self):
        """3/3 KHÔNG được đè 9/10: khóa sort chính là SỐ TRẬN tham gia."""
        events = [self._completed_event(days_ago=i + 1) for i in range(10)]
        vet = make_member("Chín Trận", days_ago=365)     # 9/10 = 90%
        newcomer = make_member("Ba Trận", days_ago=4)     # 3/3 = 100%, đủ min 3 để xếp hạng
        for i, ev in enumerate(events):
            if i < 9:
                Attendance.objects.create(war_event=ev, member=vet, status="joined")
            if i < 3:
                Attendance.objects.create(war_event=ev, member=newcomer, status="joined")
        rows = stats.build_participation(stats.completed_war_events())
        ranked, _ = stats.rank_rows(rows)
        names = [r["member"].display_name for r in ranked]
        self.assertLess(names.index("Chín Trận"), names.index("Ba Trận"))

    def test_tiebreak_by_ratio(self):
        """Cùng số trận tham gia -> tỷ lệ cao hơn đứng trên (8/9 trên 8/10)."""
        events = [self._completed_event(days_ago=i + 1) for i in range(10)]
        a = make_member("Tám Mười", days_ago=365)
        b = make_member("Tám Chín", days_ago=365)
        Member.objects.filter(pk=b.pk).update(
            created_at=stats._event_moment(events[-1]) + timedelta(minutes=1)  # lỡ đúng trận cũ nhất
        )
        for i, ev in enumerate(events):
            if i < 8:
                Attendance.objects.create(war_event=ev, member=a, status="joined")
                Attendance.objects.create(war_event=ev, member=b, status="joined")
        ranked, _ = stats.rank_rows(stats.build_participation(stats.completed_war_events()))
        names = [r["member"].display_name for r in ranked]
        self.assertLess(names.index("Tám Chín"), names.index("Tám Mười"))

    def test_tiebreak_by_earliness(self):
        """Case 5 người 9/9: hòa cả trận lẫn tỷ lệ -> ai báo danh sớm hơn (trước
        hạn nhiều hơn) xếp trên. Đo bằng created_at so với deadline_at."""
        events = []
        for i in range(3):
            ev = make_event(days_ago=i + 1, current=False)
            # deadline mỗi trận = cuối ngày event; đặt cố định để tính sớm
            ev.deadline_at = stats._event_moment(ev)
            ev.save()
            events.append(ev)
        early = make_member("Báo Sớm", days_ago=365)
        late = make_member("Báo Trễ", days_ago=365)
        for ev in events:
            lock = ev.deadline_at
            ae = Attendance.objects.create(war_event=ev, member=early, status="joined")
            al = Attendance.objects.create(war_event=ev, member=late, status="joined")
            # early báo trước hạn 3 tiếng, late chỉ trước 10 phút
            Attendance.objects.filter(pk=ae.pk).update(created_at=lock - timedelta(hours=3))
            Attendance.objects.filter(pk=al.pk).update(created_at=lock - timedelta(minutes=10))
        ranked, _ = stats.rank_rows(stats.build_participation(stats.completed_war_events()))
        names = [r["member"].display_name for r in ranked]
        # Cả hai đều 3/3 = 100%, chỉ khác thời điểm báo danh
        self.assertLess(names.index("Báo Sớm"), names.index("Báo Trễ"))


class DailyOpsTests(TestCase):
    def test_weekly_event_idempotent(self):
        """Chạy lệnh 2 lần không tạo event trùng, deadline trước giờ đánh đúng 2 tiếng."""
        from django.core.management import call_command

        call_command("daily_ops")
        call_command("daily_ops")
        events = WarEvent.objects.filter(event_type=WarEvent.EventType.WAR)
        self.assertEqual(events.count(), 1)
        ev = events.first()
        self.assertEqual(ev.event_date.weekday(), 5)  # thứ 7
        self.assertEqual(ev.battle_start_at - ev.deadline_at, timedelta(minutes=120))
        self.assertTrue(ev.is_current)


class PublicPagesTests(TestCase):
    def test_leaderboard_renders(self):
        r = Client().get("/public/leaderboard/")
        self.assertEqual(r.status_code, 200)

    def test_notify_data_endpoint(self):
        """Endpoint cho GitHub Actions: có event trả đủ trường, không event trả has_event=False."""
        r = Client().get("/public/notify-data/")
        self.assertEqual(r.json(), {"has_event": False})
        ev = make_event()
        ev.deadline_at = timezone.now() + timedelta(hours=5)
        ev.save()
        m = make_member("NotifyTest")
        Attendance.objects.create(war_event=ev, member=m, status="joined")
        d = Client().get("/public/notify-data/").json()
        self.assertTrue(d["has_event"])
        self.assertEqual(d["joined"], 1)
        self.assertEqual(d["capacity"], 60)
        self.assertIn("title", d)

    def test_live_endpoint(self):
        make_event()
        r = Client().get("/public/result/war/live/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("v", r.json())


@override_settings()
class DiscordRetryTests(TestCase):
    """Retry webhook: 429 phải thử lại, thành công giữa chừng phải dừng đúng lúc.
    Dùng mock để KHÔNG gọi mạng thật — test chạy offline, nhanh, ổn định."""

    def setUp(self):
        # Cần có URL để hàm không thoát sớm; giá trị giả vì requests bị mock.
        self.env = mock.patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": "https://x/y"})
        self.env.start()

    def tearDown(self):
        self.env.stop()

    def _resp(self, status, retry_after=None):
        r = mock.Mock()
        r.status_code = status
        r.headers = {"Retry-After": str(retry_after)} if retry_after is not None else {}
        r.json.return_value = {}
        r.raise_for_status = mock.Mock()
        return r

    @mock.patch("attendance.notify.time.sleep", return_value=None)  # bỏ chờ thật
    @mock.patch("attendance.notify.requests.post")
    def test_retry_then_success(self, mock_post, _sleep):
        from attendance.notify import send_discord
        # 429 hai lần rồi 200 -> phải trả True, gọi post đúng 3 lần
        mock_post.side_effect = [self._resp(429, 1), self._resp(429, 1), self._resp(200)]
        self.assertTrue(send_discord("hi"))
        self.assertEqual(mock_post.call_count, 3)

    @mock.patch("attendance.notify.time.sleep", return_value=None)
    @mock.patch("attendance.notify.requests.post")
    def test_gives_up_after_max(self, mock_post, _sleep):
        from attendance.notify import send_discord, MAX_ATTEMPTS
        # 429 mãi -> False, gọi đúng MAX_ATTEMPTS lần rồi bỏ
        mock_post.return_value = self._resp(429, 1)
        self.assertFalse(send_discord("hi"))
        self.assertEqual(mock_post.call_count, MAX_ATTEMPTS)

    @mock.patch("attendance.notify.time.sleep", return_value=None)
    @mock.patch("attendance.notify.requests.post")
    def test_first_try_success_no_retry(self, mock_post, _sleep):
        from attendance.notify import send_discord
        mock_post.return_value = self._resp(200)
        self.assertTrue(send_discord("hi"))
        self.assertEqual(mock_post.call_count, 1)  # không retry khi lần đầu ok

    @mock.patch("attendance.notify.time.sleep", return_value=None)
    @mock.patch("attendance.notify.requests.post")
    def test_no_retry_on_400(self, mock_post, _sleep):
        """400 (payload sai) KHÔNG được retry — retry 4xx làm IP bị Cloudflare ban nhanh hơn."""
        from attendance.notify import send_discord
        r = mock.Mock(); r.status_code = 400; r.text = '{"message":"bad"}'; r.headers = {}
        mock_post.return_value = r
        self.assertFalse(send_discord("hi", mention_everyone=True))
        self.assertEqual(mock_post.call_count, 1)  # gọi đúng 1 lần, không lặp

    @mock.patch("attendance.notify.time.sleep", return_value=None)
    @mock.patch("attendance.notify.requests.post")
    def test_retry_on_500(self, mock_post, _sleep):
        """5xx (lỗi phía Discord) thì mới retry."""
        from attendance.notify import send_discord
        ok = mock.Mock(); ok.status_code = 200; ok.headers = {}; ok.raise_for_status = mock.Mock()
        err = mock.Mock(); err.status_code = 503; err.headers = {}
        mock_post.side_effect = [err, ok]
        self.assertTrue(send_discord("hi"))
        self.assertEqual(mock_post.call_count, 2)

    def test_no_url_returns_false(self):
        from attendance.notify import send_discord
        with mock.patch.dict("os.environ", {"DISCORD_WEBHOOK_URL": ""}):
            self.assertFalse(send_discord("hi"))


@override_settings(OPS_TOKEN="test-ops-token-123")
class InternalOpsEndpointTests(TestCase):
    """Endpoint /internal/daily-ops/: bảo mật token + idempotent."""

    URL = "/internal/daily-ops/"

    def setUp(self):
        cache.clear()

    def _post(self, token=None):
        headers = {"HTTP_AUTHORIZATION": f"Bearer {token}"} if token else {}
        return Client().post(self.URL, **headers)

    def test_no_token_forbidden(self):
        self.assertEqual(self._post().status_code, 403)

    def test_wrong_token_forbidden(self):
        self.assertEqual(self._post("sai-token").status_code, 403)

    @override_settings(OPS_TOKEN="")
    def test_disabled_when_no_token_configured(self):
        """Không khai OPS_TOKEN trong .env -> endpoint tự khóa, kể cả gửi gì cũng 403."""
        self.assertEqual(self._post("bat-ky").status_code, 403)

    def test_correct_token_creates_event_idempotent(self):
        r1 = self._post("test-ops-token-123")
        self.assertEqual(r1.status_code, 200)
        self.assertTrue(r1.json()["ok"])
        r2 = self._post("test-ops-token-123")
        self.assertFalse(r2.json()["event_created"])  # lần 2 không tạo trùng
        self.assertEqual(
            WarEvent.objects.filter(event_type=WarEvent.EventType.WAR).count(), 1
        )
        ev = WarEvent.objects.get()
        self.assertEqual(ev.event_date.weekday(), 5)  # thứ 7
        self.assertTrue(ev.is_current)

    def test_get_method_not_allowed(self):
        r = Client().get(self.URL)
        self.assertEqual(r.status_code, 405)
