"""
Django settings for PopUp Plug.

Everything environment-specific comes from environment variables (see .env.example),
so the same code runs locally (SQLite, local media, console email) and on Render
(Postgres on Supabase, S3-compatible storage on Backblaze B2, SMTP via Brevo).
"""
import os
import sys
from pathlib import Path
from urllib.parse import urlparse

import dj_database_url
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def getenv(name, default=""):
    """Like os.environ.get, but an empty value (`NAME=` in .env) counts as 'not set'."""
    value = os.environ.get(name, "")
    return value.strip() if value.strip() else default


def env_bool(name, default=False):
    return getenv(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


def env_list(name, default=""):
    return [v.strip() for v in getenv(name, default).split(",") if v.strip()]


# Render sets RENDER=true automatically. Locally DEBUG defaults to on, on Render to off.
ON_RENDER = bool(getenv("RENDER"))

# ---------------------------------------------------------------------------
# Core
# ---------------------------------------------------------------------------
DEBUG = env_bool("DEBUG", not ON_RENDER)
SECRET_KEY = getenv("SECRET_KEY", "dev-only-insecure-key-change-me")
if not DEBUG and SECRET_KEY == "dev-only-insecure-key-change-me":
    raise RuntimeError("Set a real SECRET_KEY in production.")

# Public site URL: used for absolute links in emails, Open Graph tags and Instagram cards.
SITE_URL = getenv("SITE_URL", "http://localhost:8000").rstrip("/")
SITE_NAME = getenv("SITE_NAME", "PopUp Plug")
_site_host = urlparse(SITE_URL).hostname or ""

ALLOWED_HOSTS = env_list("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver")
CSRF_TRUSTED_ORIGINS = env_list("CSRF_TRUSTED_ORIGINS")

# Hosts are added automatically, so there's nothing to configure for the Render URL
# or for your custom domain (set SITE_URL=https://popupplug.com.ng).
_render_host = getenv("RENDER_EXTERNAL_HOSTNAME")
if _render_host:
    ALLOWED_HOSTS.append(_render_host)
    CSRF_TRUSTED_ORIGINS.append(f"https://{_render_host}")
if _site_host and _site_host not in ("localhost", "127.0.0.1"):
    for host in (_site_host, f"www.{_site_host}" if not _site_host.startswith("www.") else _site_host[4:]):
        ALLOWED_HOSTS.append(host)
        CSRF_TRUSTED_ORIGINS.append(f"https://{host}")

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "core",
    "vendors",
    "events",
    "desk",
    "social",
]

MIDDLEWARE = [
    "core.middleware.HealthCheckMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "config.context_processors.site",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------------------
# Database: SQLite locally, Postgres (Supabase) via DATABASE_URL
# ---------------------------------------------------------------------------
_db_url = getenv("DATABASE_URL")
if _db_url:
    DATABASES = {
        "default": dj_database_url.parse(
            _db_url,
            conn_max_age=600,
            conn_health_checks=True,
            ssl_require=_db_url.startswith(("postgres://", "postgresql://")) and not DEBUG,
        )
    }
else:  # local development: a SQLite file next to manage.py
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}
# Supabase's transaction pooler (port 6543) doesn't support server-side cursors or
# persistent connections. The session pooler (port 5432) is the recommended choice.
if DATABASES["default"].get("PORT") in (6543, "6543"):
    DATABASES["default"]["DISABLE_SERVER_SIDE_CURSORS"] = True
    DATABASES["default"]["CONN_MAX_AGE"] = 0

# ---------------------------------------------------------------------------
# Cache: in-memory by default, Redis if REDIS_URL is set.
# (In-memory is per process, so production runs ONE gunicorn worker with threads.
# See render.yaml. If you scale to several workers, set REDIS_URL.)
# ---------------------------------------------------------------------------
if getenv("REDIS_URL"):
    CACHES = {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": os.environ["REDIS_URL"],
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
        }
    }
else:
    CACHES = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}

# How long (seconds) public list pages are cached for anonymous visitors. 0 disables it.
PUBLIC_PAGE_CACHE_SECONDS = int(getenv("PUBLIC_PAGE_CACHE_SECONDS", "120"))

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "vendors:dashboard"
LOGOUT_REDIRECT_URL = "events:home"

# ---------------------------------------------------------------------------
# i18n / time: Lagos
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-ng"
TIME_ZONE = "Africa/Lagos"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static + media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"
if "test" in sys.argv[1:2]:  # `manage.py test` must not litter ./media
    import tempfile
    MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="popupplug-test-media-"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
        if not DEBUG
        else "django.contrib.staticfiles.storage.StaticFilesStorage"
    },
}

# Uploaded images go to an S3-compatible bucket (Backblaze B2, Cloudflare R2, AWS S3)
# when AWS_STORAGE_BUCKET_NAME is set. Render's disk is wiped on every deploy, so a
# bucket is REQUIRED in production. The bucket must be public (images are shown on
# the site and fetched by Instagram).
USING_BUCKET = bool(getenv("AWS_STORAGE_BUCKET_NAME"))
if USING_BUCKET:
    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}
    AWS_STORAGE_BUCKET_NAME = os.environ["AWS_STORAGE_BUCKET_NAME"]
    AWS_S3_ENDPOINT_URL = getenv("AWS_S3_ENDPOINT_URL") or None
    AWS_S3_REGION_NAME = getenv("AWS_S3_REGION_NAME") or None
    AWS_S3_CUSTOM_DOMAIN = getenv("AWS_S3_CUSTOM_DOMAIN") or None
    AWS_S3_SIGNATURE_VERSION = "s3v4"
    AWS_DEFAULT_ACL = None
    AWS_QUERYSTRING_AUTH = False
    AWS_S3_FILE_OVERWRITE = False
    AWS_S3_OBJECT_PARAMETERS = {"CacheControl": "public, max-age=31536000, immutable"}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Upload limits and spam control
# ---------------------------------------------------------------------------
MAX_UPLOAD_BYTES = 8 * 1024 * 1024  # reject images bigger than 8 MB
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
MAX_EVENTS_PER_DAY = int(getenv("MAX_EVENTS_PER_DAY", "5"))

# ---------------------------------------------------------------------------
# Email. Three modes, picked automatically:
#   BREVO_API_KEY set  -> Brevo HTTPS API (use this on Render's free plan: it blocks SMTP ports)
#   EMAIL_HOST set     -> plain SMTP (any provider, works anywhere SMTP isn't blocked)
#   neither            -> emails are printed to the console (local development)
# ---------------------------------------------------------------------------
BREVO_API_KEY = getenv("BREVO_API_KEY")
EMAIL_HOST = getenv("EMAIL_HOST")
if BREVO_API_KEY:
    EMAIL_BACKEND = "core.brevo_backend.BrevoEmailBackend"
elif EMAIL_HOST:
    EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
    EMAIL_PORT = int(getenv("EMAIL_PORT", "587"))
    EMAIL_HOST_USER = getenv("EMAIL_HOST_USER")
    EMAIL_HOST_PASSWORD = getenv("EMAIL_HOST_PASSWORD")
    EMAIL_USE_TLS = env_bool("EMAIL_USE_TLS", True)
    EMAIL_TIMEOUT = 10
else:
    EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
DEFAULT_FROM_EMAIL = getenv("DEFAULT_FROM_EMAIL", f"{SITE_NAME} <no-reply@popupplug.com.ng>")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# Who gets "new vendor signed up" alerts. Falls back to the emails of staff users.
ADMIN_NOTIFY_EMAILS = env_list("ADMIN_NOTIFY_EMAILS")
# Send emails in a background thread so a slow SMTP server never slows a page.
NOTIFY_ASYNC = env_bool("NOTIFY_ASYNC", True)

# ---------------------------------------------------------------------------
# Instagram auto-posting (see DEPLOY.md, "Instagram")
# ---------------------------------------------------------------------------
INSTAGRAM_ENABLED = env_bool("INSTAGRAM_ENABLED", False)        # master switch
INSTAGRAM_AUTOPOST = env_bool("INSTAGRAM_AUTOPOST", False)      # post as soon as an event is approved
INSTAGRAM_DRY_RUN = env_bool("INSTAGRAM_DRY_RUN", False)        # build card + caption, don't call Instagram
INSTAGRAM_USER_ID = getenv("INSTAGRAM_USER_ID", "")
INSTAGRAM_ACCESS_TOKEN = getenv("INSTAGRAM_ACCESS_TOKEN", "")  # seeds the stored token
INSTAGRAM_API_HOST = getenv("INSTAGRAM_API_HOST", "https://graph.instagram.com").rstrip("/")
INSTAGRAM_API_VERSION = getenv("INSTAGRAM_API_VERSION", "")  # optional, e.g. v23.0
INSTAGRAM_HANDLE = getenv("INSTAGRAM_HANDLE", "thepopupplug.ng")

# ---------------------------------------------------------------------------
# Logging: everything to the console, which is where Render shows logs.
# ---------------------------------------------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"plain": {"format": "%(asctime)s %(levelname)s %(name)s: %(message)s"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "plain"}},
    "root": {"handlers": ["console"], "level": getenv("LOG_LEVEL", "INFO")},
}

# ---------------------------------------------------------------------------
# Production security
# ---------------------------------------------------------------------------
if not DEBUG:
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
    SECURE_REDIRECT_EXEMPT = [r"^healthz/?$"]  # uptime monitors and Render health checks
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_CONTENT_TYPE_NOSNIFF = True