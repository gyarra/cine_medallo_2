# Cine Medallo

Django service that tracks movie theaters, movies, and showtimes in Medellín, Colombia.

## Tech Stack

- Django 6.0
- Celery 5.4
- PostgreSQL (Supabase)
- Redis
- Python 3.13

## Setup

```bash
# Run the setup script (installs uv, dependencies, and Camoufox browser)
./scripts/setup.sh

# Activate virtual environment
source .venv/bin/activate

# Set up environment variables
cp .env.example .env  # Then edit with your values

# Run migrations
python manage.py migrate

# Load theater data
python manage.py load_theaters
```

## Running the Server

```bash
python manage.py runserver
```

## Running Tests

Tests always use SQLite (configured in `config/settings_test.py`), so they never touch the production database.

```bash
# Run all tests
pytest

# Run specific test file
pytest movies_app/tasks/tests/test_colombia_com_download_task.py -v

# Run specific test
pytest movies_app/tasks/tests/ -k "test_extracts_movie_names" -v

# Run test with debug level output
pytest movies_app/tasks/tests/ -k "test_extracts_movie_names" -v -s --log-cli-level=DEBUG
```

### Viewing Logs During Tests

By default, logs are captured but not displayed. To see logs while debugging:

```bash
# Show logs at DEBUG level in real-time
pytest movies_app/tasks/tests/ -v --log-cli-level=DEBUG

# Show logs at INFO level
pytest movies_app/tasks/tests/ -v --log-cli-level=INFO

# Also show print statements
pytest movies_app/tasks/tests/ -v -s --log-cli-level=DEBUG
```

## Code Quality

Run these before committing:

```bash
ruff check .
pyright
pytest
```

## Management Commands

```bash
# Load theaters from seed data
python manage.py load_theaters

# Search TMDB for a movie
python manage.py tmdb_service_search "Avatar"

# Import a movie from TMDB
python manage.py tmdb_service_import_movie <tmdb_id>

# Delete a movie and its showtimes
python manage.py delete_movie <movie_id>
python manage.py delete_movie --slug <movie-slug>
python manage.py delete_movie --tmdb-id <tmdb_id>

# Download showtimes from colombia.com
python manage.py colombia_com_run_download_task
```
