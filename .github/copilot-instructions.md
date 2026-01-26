# Copilot Instructions

## Project Overview

Django service that tracks movie theaters, movies, and showtimes in Medellín, Colombia. Developed on macOS.

**No external customers.** Internal tool—no backwards compatibility concerns. Delete deprecated code immediately.

### Tech Stack
Django 6.0 · Celery 5.4 · PostgreSQL · Redis · Python 3.13 · Django REST Framework

## Essential Commands
```bash
uv sync --extra dev
source .venv/bin/activate
ruff check .
pyright
pytest
```

## Hard Rules

* Use OOP—classes, not free functions; composition over inheritance
* No default values in method parameters
* Never swallow exceptions—log errors properly
* Keep comments minimal
* **NO inline imports**—all imports at top of file, no exceptions
* Avoid synchronous calls in asynchronous code (use await for all I/O operations)
* Always run `ruff check .`, `pyright`, `pytest` before committing and pushing
* Generate migrations before pushing a PR
* If blocked, ask user—don't claim work complete when blocked


## Comments and Docstrings

* Most methods need no docstring—code should be self-explanatory
* Write comments only for non-obvious behavior or important constraints
* Do not describe what the code does; describe why if unclear
* Exceptions: Management command files should have verbose docs with examples at the top
* Logger statements ending in "\n\n" are fine to keep log separation clear


## Command Line Conventions

Run commands separately (not with `&&`). Combined commands fail auto-allow:
**NOT CORRECT:**
```bash
source .venv/bin/activate && pytest movies_app/tests/test_models.py
```

**CORRECT:**
```bash
source .venv/bin/activate
pytest movies_app/tests/test_models.py
```

## Documentation

Do not add large amounts of code to documention files when you can point to a file to emulate.


## Testing

Pre-commit checks:
```bash
ruff check .
pyright
python manage.py check
python manage.py makemigrations --check --dry-run
pytest
```

* Use pytest fixtures from `conftest.py`—not `Model.objects.create()`
* Run tests with `pytest -v <file> -k <name>` (NOT `python -m pytest`)
* Run the associated management command to manually verify before completing work
* New features require success and failure tests
* Write integration tests in addition to unit tests for complex logic

## Error Handling

* Fail fast and loudly rather than silently handle problems that should be fixed
* Only catch exceptions if recovery is possible. If there's an exception that should never happen, let it raise and break the app.
* Only check for None values if it is expected that they may be None. It's better to crash on unexpected None.
* Always log when catching exceptions
* Let exceptions propagate for proper failure tracking
* Log operational issues to `OperationalIssue` model for most issues. We want to know what is going wrong so we can fix it.

## Architecture

```
cine_medallo_2/
├── config/          # Django project settings
├── movies_app/      # Core app (Theater, Movie, Showtime models)
│   ├── models/
│   ├── views/
│   ├── serializers/
│   └── tests/
└── docs/            # Requirements and documentation
```

### Database

* Use `select_related()` and `prefetch_related()`
* Wrap multi-step operations in `@transaction.atomic`
* All showtimes stored as timezone-aware datetimes (UTC)

## Platform

* Development on **macOS**
