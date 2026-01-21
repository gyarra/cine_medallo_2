# Dependencies Audit Report

**Date:** 2026-01-21
**Python Version:** 3.13
**Package Manager:** uv

## Executive Summary

| Category | Status |
|----------|--------|
| Security Vulnerabilities | None found |
| Outdated Packages | Minor (transitive only) |
| Unused Dependencies | 7 packages identified |
| Potential Savings | ~15MB install size |

---

## Security Analysis

**Result:** No known vulnerabilities found (via pip-audit)

All direct and transitive dependencies are free of known CVEs.

---

## Outdated Packages

Only transitive dependencies have minor updates available:

| Package | Current | Latest | Type |
|---------|---------|--------|------|
| packaging | 25.0 | 26.0 | transitive |
| soupsieve | 2.8.2 | 2.8.3 | transitive |
| wcwidth | 0.2.14 | 0.3.0 | transitive |

**Recommendation:** No action required. These will update automatically when running `uv sync`.

---

## Unnecessary Dependencies (Recommended Removals)

### 1. `amqp>=5.3.1` - REMOVE
- **Status:** Not directly imported
- **Reason:** Celery brings this as a transitive dependency automatically
- **Impact:** None - will still be installed via Celery

### 2. `asgiref>=3.10.0` - REMOVE
- **Status:** Not directly imported
- **Reason:** Django brings this as a transitive dependency
- **Impact:** None - will still be installed via Django

### 3. `playwright>=1.55.0` - REMOVE
- **Status:** Not directly imported (camoufox is used instead)
- **Reason:** camoufox already depends on playwright
- **Impact:** None - will still be installed via camoufox

### 4. `django-cors-headers>=4.7.0` - REMOVE
- **Status:** Not imported, not in INSTALLED_APPS
- **Reason:** Package is installed but never configured or used
- **Impact:** ~50KB savings
- **Note:** Add back when API needs CORS support

### 5. `djangorestframework>=3.16.0` - REMOVE
- **Status:** Not imported, not in INSTALLED_APPS
- **Reason:** Package is installed but never configured or used
- **Impact:** ~3.7MB savings
- **Note:** Add back when building REST APIs

### 6. `python-dateutil>=2.9.0.post0` - REMOVE
- **Status:** Not imported anywhere in codebase
- **Reason:** Celery brings this as a transitive dependency
- **Impact:** None - will still be installed via Celery

### 7. `psycopg2-binary>=2.9.11` - REMOVE (choose one)
- **Status:** Neither psycopg nor psycopg2 are directly imported
- **Reason:** Both PostgreSQL drivers are listed; only one is needed
- **Recommendation:** Keep `psycopg>=3.2.12` (modern, async-capable)
- **Impact:** ~11MB savings (psycopg2-binary libs)

---

## Dependency Size Analysis

Top packages by installed size:

| Package | Size | Notes |
|---------|------|-------|
| playwright | 129MB | Required by camoufox (browser automation) |
| numpy | 55MB | Required by camoufox |
| django | 33MB | Core framework - required |
| lxml | 12MB | Required for HTML parsing |
| psycopg2-binary | 11MB | **Redundant** - remove |
| rest_framework | 3.7MB | **Unused** - remove |

**Note:** The large size of playwright/numpy is unavoidable if using camoufox for web scraping.

---

## Recommended `pyproject.toml` Changes

```toml
[project]
dependencies = [
    "beautifulsoup4>=4.14.2",
    "camoufox>=0.4.11",
    "celery>=5.4.0",
    "dj-database-url>=2.3.0",
    "Django>=5.2.7",
    "gunicorn>=23.0.0",
    "lxml>=6.0.2",
    "psycopg>=3.2.12",
    "python-dotenv>=1.2.1",
    "requests>=2.32.5",
]
```

### Packages Removed (7):
1. `amqp` - transitive of celery
2. `asgiref` - transitive of django
3. `playwright` - transitive of camoufox
4. `django-cors-headers` - unused
5. `djangorestframework` - unused
6. `python-dateutil` - transitive of celery
7. `psycopg2-binary` - redundant with psycopg

---

## Future Considerations

### When to re-add removed packages:

- **django-cors-headers**: When building a frontend that makes cross-origin requests
- **djangorestframework**: When building REST APIs (currently only using Django views)

### Heavy dependencies to monitor:

The `camoufox` package brings significant dependencies:
- playwright (~129MB) - browser automation
- numpy (~55MB) - numerical computing
- Plus: browserforge, orjson, pyyaml, screeninfo, tqdm, etc.

If web scraping requirements change, consider lighter alternatives like:
- `httpx` + `selectolax` for simple HTTP scraping
- `requests-html` for JavaScript rendering without full browser

---

## Action Items

1. [ ] Update `pyproject.toml` with recommended changes
2. [ ] Run `uv sync` to update lock file
3. [ ] Run tests to verify no regressions
4. [ ] Consider if REST framework features are needed soon
