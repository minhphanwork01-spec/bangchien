# Deploy BangCheck

BangCheck là Django app nhẹ, không cần npm/build frontend.

## Files liên quan

- `requirements.txt`
- `Procfile`
- `.env.example`
- `bangcheck/settings.py`

## Environment variables

```env
DEBUG=False
SECRET_KEY=change-me
ALLOWED_HOSTS=your-domain.com
CSRF_TRUSTED_ORIGINS=https://your-domain.com
DATABASE_URL=postgresql://user:password@host:5432/dbname
DB_SSL_REQUIRE=True
TIME_ZONE=Asia/Ho_Chi_Minh
```

Local/dev không có `DATABASE_URL` thì dùng SQLite.

## Render/Koyeb/Railway-style deploy

Build command:

```bash
pip install -r requirements.txt && python manage.py collectstatic --noinput
```

Start command:

```bash
gunicorn bangcheck.wsgi:application
```

Post-deploy:

```bash
python manage.py migrate
python manage.py createsuperuser
```

## PythonAnywhere

1. Tạo virtualenv.
2. `pip install -r requirements.txt`.
3. Web app trỏ về `bangcheck/wsgi.py`.
4. Static URL `/static/` trỏ tới thư mục `static/` hoặc chạy `collectstatic` rồi trỏ tới `staticfiles/`.
5. Chạy `python manage.py migrate` và `createsuperuser`.

## Backup

Free tier DB/hosting có thể giới hạn hoặc reset. Nên export CSV sau mỗi tuần hoặc backup DB định kỳ.


## UI consolidation release

No database migration is required for this release.

After uploading:

```bash
python manage.py collectstatic --noinput
python manage.py check
```

Reload the PythonAnywhere web app after collectstatic completes.

## Security update (bản này)

Đã thêm `django-axes` (chống brute force login) và `django-ratelimit` (chống spam endpoint public).

Sau khi pull bản này:

```bash
pip install -r requirements.txt
python manage.py migrate   # axes cần bảng riêng
```

Env mới cần lưu ý:

- `DEBUG` giờ mặc định **False**. Local dev phải có `DEBUG=True` trong `.env`.
- `SECRET_KEY` **bắt buộc** khi chạy production (app từ chối khởi động nếu thiếu).
- `FEEDBACK_HASH_SALT` (khuyến nghị): salt riêng cho hash feedback, để sau này rotate SECRET_KEY không phá dedup feedback.
- `SECURE_SSL_REDIRECT` mặc định True khi production; nếu hosting đã tự redirect HTTPS và bị vòng lặp thì set `SECURE_SSL_REDIRECT=False`.

Login sai 5 lần liên tiếp (theo cặp IP + username) sẽ bị khóa 15 phút. Gỡ khóa thủ công: `python manage.py axes_reset`.
