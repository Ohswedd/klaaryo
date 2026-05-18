import os
from pathlib import Path
from urllib.parse import urlparse

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "dev-insecure-key")
DEBUG = True
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "routingapp",
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"json": {"()": "routingapp.logging_config.JsonLineFormatter"}},
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"handlers": ["console"], "level": "INFO"},
}

_db = urlparse(os.environ["DATABASE_URL"])
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": _db.path.lstrip("/"),
        "USER": _db.username,
        "PASSWORD": _db.password,
        "HOST": _db.hostname,
        "PORT": _db.port or 5432,
    }
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = False
USE_TZ = True

PUBSUB_PROJECT_ID = os.environ.get("PUBSUB_PROJECT_ID", "klaaryo-local")
PUBSUB_SUBSCRIPTION_RECEIVED = "routing.candidate-received-sub"
PUBSUB_TOPIC_ROUTED = "candidate.routed"
CONFIG_GRPC_ADDR = os.environ.get("CONFIG_GRPC_ADDR", "config:50051")
