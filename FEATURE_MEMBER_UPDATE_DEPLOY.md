# Member update request feature

## Chức năng
- Member đang được chọn tại `/checkin/war/` có nút `Thay đổi thông tin`.
- Form mở trong modal desktop và bottom sheet mobile.
- User gửi tên/phái đề xuất, không sửa trực tiếp Member.
- Chặn request rỗng, tên trùng và request update pending trùng.
- Leader xử lý chung tại `/leader/member-requests/`.
- Có filter `Tạo mới` và `Chỉnh thông tin`.
- Khi duyệt update, Member mới được cập nhật.
- Lưu snapshot cũ, người xử lý, thời gian xử lý và ghi chú xử lý.

## File cần upload
- `attendance/models.py`
- `attendance/forms.py`
- `attendance/services.py`
- `attendance/views.py`
- `attendance/urls.py`
- `attendance/admin.py`
- `attendance/migrations/0007_member_update_requests.py`
- `templates/checkin_status.html`
- `templates/leader_member_requests.html`
- `static/css/public.css`
- `static/css/leader.css`
- `static/css/responsive.css`

## Không upload đè
- `db.sqlite3`
- các migration `0001` đến `0006`
- file cấu hình môi trường production

## Bash trên PythonAnywhere
```bash
cd /home/frozenabs/bangchien
source /home/frozenabs/.virtualenvs/bangchien/bin/activate

python manage.py check
python manage.py showmigrations attendance
python manage.py migrate --plan
python manage.py migrate attendance
python manage.py collectstatic --noinput
python manage.py check
python manage.py showmigrations attendance
```

Kết quả cuối cần có `[X] 0007_member_update_requests`.
