# Index name fix

Upload:
- attendance/models.py
- attendance/migrations/0007_member_update_requests.py

Do not upload db.sqlite3.

Run:
python manage.py check
python manage.py migrate --plan
python manage.py migrate attendance
python manage.py collectstatic --noinput
python manage.py check
