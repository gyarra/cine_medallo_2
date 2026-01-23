"""
Test settings - always uses SQLite, never touches production database.
"""

from config.settings import *  # noqa: F401, F403

# Force SQLite for all tests - ignore DATABASE_URL entirely
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "test_db.sqlite3",  # noqa: F405
    }
}

# Faster password hashing for tests
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Logging: Let pytest capture logs (don't use NullHandler)
# Use --log-cli-level=DEBUG or -o log_cli=true to see logs during tests
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "simple": {
            "format": "{levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        "movies_app": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
