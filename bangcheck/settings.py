"""
BangCheck settings.

Local/dev defaults to SQLite. Production can use PostgreSQL through DATABASE_URL.
This keeps the project simple for PythonAnywhere/Render/Koyeb-style hosting.

Security defaults:
- DEBUG mặc định False. Local dev phải set DEBUG=True trong .env.
- SECRET_KEY bắt buộc khi DEBUG=False (không cho chạy production với key dev).
- django-axes chống brute force login, django-ratelimit chống spam endpoint public.
"""
import os
from pathlib import Path

import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]


_DEV_SECRET_KEY = "django-insecure-bangcheck-dev-key-change-in-production"

DEBUG = env_bool("DEBUG", False)
# `or`: coi SECRET_KEY= rỗng trong .env như chưa set
SECRET_KEY = os.getenv("SECRET_KEY") or (_DEV_SECRET_KEY if DEBUG else "")

if not DEBUG and (not SECRET_KEY or SECRET_KEY in {_DEV_SECRET_KEY, "change-me"}):
    raise ImproperlyConfigured(
        "SECRET_KEY chưa được set. Có 2 trường hợp:\n"
        "  1) Đang chạy LOCAL DEV: tạo file .env từ mẫu (cp .env.example .env) — "
        "trong đó đã có DEBUG=True, không cần SECRET_KEY.\n"
        "  2) Đang deploy PRODUCTION: set SECRET_KEY trong .env, tạo bằng:\n"
        "     python -c \"import secrets; print(secrets.token_urlsafe(50))\""
    )

# Salt riêng cho hash feedback/device/ip. Fallback SECRET_KEY để tương thích dữ liệu cũ,
# nhưng nên set FEEDBACK_HASH_SALT riêng để rotate SECRET_KEY không phá dedup feedback.
FEEDBACK_HASH_SALT = os.getenv("FEEDBACK_HASH_SALT") or SECRET_KEY

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "127.0.0.1,localhost")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "axes",
    "attendance",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Gán mã trình duyệt cho khu quản trị (phân biệt máy khi dùng chung account).
    "attendance.admin_audit.AdminBrowserIdMiddleware",
    # Axes phải nằm cuối để nhìn thấy request đã qua auth middleware.
    "axes.middleware.AxesMiddleware",
]

# ── Chống brute force login (leader + /admin/) ──────────────
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",  # phải đứng đầu
    "django.contrib.auth.backends.ModelBackend",
]
AXES_FAILURE_LIMIT = 5           # 5 lần sai
AXES_COOLOFF_TIME = 0.25         # khóa 15 phút (đơn vị: giờ)
AXES_LOCKOUT_PARAMETERS = [["ip_address", "username"]]  # khóa theo cặp IP+username
AXES_RESET_ON_SUCCESS = True
AXES_LOCKOUT_TEMPLATE = "registration/lockout.html"

# django-ratelimit dùng cache. LocMemCache đủ cho PythonAnywhere (ít worker).
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "bangcheck-cache",
    }
}

ROOT_URLCONF = "bangcheck.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "bangcheck.wsgi.application"

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.parse(
            DATABASE_URL,
            conn_max_age=600,
            ssl_require=env_bool("DB_SSL_REQUIRE", False),
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "vi"
TIME_ZONE = os.getenv("TIME_ZONE", "Asia/Ho_Chi_Minh")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
import sys as _sys

_TESTING = "test" in _sys.argv
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    # Khi chạy test: dùng storage thường để không đòi collectstatic trước.
    "staticfiles": {
        "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        if _TESTING
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/leader/dashboard/"
LOGOUT_REDIRECT_URL = "/checkin/"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# ── Production hardening (chỉ bật khi DEBUG=False) ─────────
if not DEBUG:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = False
    SESSION_COOKIE_HTTPONLY = True
    SECURE_REFERRER_POLICY = "same-origin"


# ── Logging: ghi file logs/app.log, xoay vòng 2MB x 3 file ──
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(exist_ok=True)
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "{asctime} {levelname} {name} {message}", "style": "{"},
    },
    "handlers": {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": LOG_DIR / "app.log",
            "maxBytes": 2 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "verbose",
            "encoding": "utf-8",
        },
    },
    "loggers": {
        "django": {"handlers": ["file"], "level": "WARNING", "propagate": True},
        "bangcheck": {"handlers": ["file"], "level": "INFO", "propagate": False},
        "axes": {"handlers": ["file"], "level": "INFO", "propagate": False},
    },
}


# Django đặt tag của messages.error() là "error", nhưng Bootstrap 5 dùng
# "danger" — không map thì render ra class alert-error (không tồn tại), mất
# nền đỏ và viền, thông báo lỗi trông như chữ trần, người dùng không nhận ra.
from django.contrib.messages import constants as _message_constants  # noqa: E402

MESSAGE_TAGS = {
    _message_constants.ERROR: "danger",
    _message_constants.DEBUG: "secondary",
}
