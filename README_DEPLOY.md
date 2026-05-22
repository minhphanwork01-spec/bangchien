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
