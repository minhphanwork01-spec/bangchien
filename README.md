# 🏰 BangCheck

Web điểm danh bang chiến hằng tuần cho bang/hội game MMORPG.

Mục tiêu: member báo danh nhanh, leader xem quân số và xếp squad/team theo từng tuần. Project dùng Django templates + vanilla JS, không dùng npm/React/Next.js.

---

## Tính năng chính

| Nhóm | Tính năng |
|---|---|
| Member | Chọn nhân vật từ danh sách sạch, cookie nhớ nhân vật, báo danh `Tham gia` hoặc `Không tham gia` |
| Public | Xem kết quả điểm danh thu gọn + squad leader đã xếp, read-only |
| Leader | Dashboard, sửa trạng thái, export CSV, copy summary |
| Squad | 4 tab: Team thủ / công / mid / vật tư, mỗi tab 30 ô, layout 5 cột x 6 người |
| Note chiến thuật | Note chung theo từng team/tab + note skill riêng từng người theo event |
| Data | Attendance lưu bằng `member_id`, không lưu bằng text name nhập tay |

---

## Stack

- Python 3.11+
- Django 5.1/5.2
- SQLite local/dev
- PostgreSQL qua `DATABASE_URL` khi deploy
- Bootstrap CDN + CSS/JS thuần
- Gunicorn + WhiteNoise cho deploy

---

## Chạy local

```bash
python -m venv .venv

# Windows
.venv\Scripts\activate

# macOS/Linux
source .venv/bin/activate

pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_data
python manage.py createsuperuser
python manage.py runserver
```

Nếu muốn reset demo:

```bash
python manage.py seed_demo_data --reset
```

---

## URL chính

| URL | Mô tả |
|---|---|
| `/checkin/` | Member báo danh |
| `/public/result/` | Public xem điểm danh + squad |
| `/member-request/` | Yêu cầu thêm nhân vật |
| `/leader/dashboard/` | Dashboard leader |
| `/leader/party-board/` | Kéo-thả xếp squad, note team/note skill |
| `/leader/events/` | Quản lý event hiện tại |
| `/leader/member-requests/` | Duyệt yêu cầu member |
| `/leader/export-csv/` | Export CSV |
| `/admin/` | Django Admin |

---

## Quy trình dùng

### Member

1. Mở `/checkin/`.
2. Tìm và chọn đúng nhân vật.
3. Bấm `Tham gia` hoặc `Không tham gia`.

Không có ô nhập lý do vắng. App này không phải hệ thống chấm công.

### Leader

1. Vào `/leader/dashboard/` để xem tổng quan.
2. Vào `/leader/party-board/` để kéo-thả người đã báo `Tham gia` vào squad.
3. Mỗi tab team có note chung riêng.
4. Mỗi member trong squad có thể có note skill ngắn riêng, ví dụ `Đả hổ + tuyệt kỹ Tố`.
5. Public chỉ xem squad, không chỉnh được.

---

## Deploy nhanh

Project đọc cấu hình từ biến môi trường:

```env
DEBUG=False
SECRET_KEY=your-secret-key
ALLOWED_HOSTS=your-domain.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com
DATABASE_URL=postgresql://user:password@host:5432/dbname
DB_SSL_REQUIRE=True
```

Lệnh deploy thường dùng:

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser
```

Chạy app bằng:

```bash
gunicorn bangcheck.wsgi:application
```

`Procfile` đã có sẵn cho Render/Railway/Koyeb-style platforms.

---

## Database model chính

```text
Member              Danh sách nhân vật chuẩn
WarEvent            Event bang chiến theo tuần, có team_notes
Attendance          Điểm danh + vị trí squad theo event
AttendanceAuditLog  Log đổi trạng thái
MemberRequest       Yêu cầu thêm nhân vật
```

Một người có thể ở vị trí squad khác nhau theo từng event vì `battle_team` và `battle_position` nằm trên `Attendance`, không nằm trên `Member`.

---

## Ghi chú maintain

- `Attendance.note` vẫn còn trong database để tương thích migration cũ, nhưng đã bị ẩn khỏi UI/export/admin flow chính.
- `Member.role`, `Member.team`, `Member.battle_team`, `Member.battle_position` vẫn giữ để tránh phá migration cũ, nhưng flow squad hiện tại dùng `Attendance.battle_team` và `Attendance.battle_position`.
- Nếu muốn clean schema triệt để sau này, tạo migration mới để xóa các legacy fields này sau khi app đã ổn định.

## Feedback sau bang chiến

- Member/public có thể gửi feedback tại `/feedback/` sau giờ bang chiến.
- Không có rating, chỉ có nội dung text.
- App tự gắn feedback vào event gần nhất đã đến giờ đánh, không bắt user chọn event.
- Nếu `WarEvent.battle_start_at` trống, app mặc định mở feedback lúc 19:00 ngày bang chiến.
- Cùng một trình duyệt/device cookie có thể sửa lại feedback đã gửi cho event đó.
- Leader xem feedback tại `/leader/feedback/`.
- Leader chỉ thấy nội dung, thời gian và event; không thấy member/device/IP.
- Server owner/dev có thể export audit hash qua shell:

```bash
python manage.py export_feedback_audit
python manage.py export_feedback_audit --event 12 --output feedback_event_12.csv
```

Khi deploy update feature này trên server đang có DB thật, chạy backup trước rồi migrate:

```bash
cp db.sqlite3 db_backup_before_feedback.sqlite3
source .venv/bin/activate
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Không chạy `seed_demo_data --reset`, `flush`, hoặc xóa `db.sqlite3` trên server thật.

### Event types: Bang chiến and Scrim

BangCheck now supports two check-in flows:

- `/checkin/war/` for Bang chiến.
- `/checkin/scrim/` for Scrim.

`/checkin/` is a simple activity selection page. Each event type has its own current event, so setting a Scrim as current does not replace the current Bang chiến event.

Public results are also separated:

- `/public/result/war/` shows Bang chiến attendance, squad, team notes, and member strategy notes.
- `/public/result/scrim/` shows only attendance groups: Tham gia, Không tham gia, Chưa điểm danh.

Party board and feedback are still for Bang chiến only.
