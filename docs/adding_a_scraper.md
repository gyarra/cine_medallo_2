# Adding a New Showtime Scraper

This guide explains how to add a scraper for a new movie theater website.

The key responsibilities of a scraper are:
- Save all showtimes for the group of theaters on the website being scraped
- Save any new movies encountered


## Reference Implementation

**Copy [mamm_download_task.py](../movies_app/tasks/mamm_download_task.py)** as your starting point. It demonstrates the cleanest architecture with two classes:

- `MAMMScraperAndHTMLParser` — Stateless class with static methods for I/O and HTML parsing
- `MAMMShowtimeSaver` — Coordinates scraping and persists movies/showtimes to the database

Also see:
- **[colombia_com_download_task.py](../movies_app/tasks/colombia_com_download_task.py)** — Multi-theater scraper with date selection (older structure, more complex)
- **[download_utilities.py](../movies_app/tasks/download_utilities.py)** — Shared utilities (`parse_time_string`, `fetch_page_html`, `MovieMetadata`, `TaskReport`, `BOGOTA_TZ`, `SPANISH_MONTHS_ABBREVIATIONS`)

## Architecture Overview

Each scraper follows this flow:

1. **Celery Task** — Entry point that iterates over theaters
2. **HTML Fetching** — Uses Camoufox headless browser for JavaScript-rendered content
3. **HTML Parsing** — Extracts movie names, URLs, and showtimes using BeautifulSoup
4. **Movie Lookup** — Matches scraped movies to TMDB via `MovieLookupService`
5. **Showtime Creation** — Saves showtimes with per-date atomic transactions

## Implementation Steps

### 1. Add Scraper Type

Add an entry to `MovieSourceUrl.ScraperType` in [movie_source_url.py](../movies_app/models/movie_source_url.py).

### 2. Add Theater URL Field (if needed)

If theaters need a source-specific URL field, add it to the `Theater` model. Otherwise, use the existing `download_source_url` field.

### 3. Create the Task File

Create `movies_app/tasks/{source}_download_task.py` with these components:

**Constants:**
- `SOURCE_NAME` — For logging and error tracking
- Import `BOGOTA_TZ` and `SPANISH_MONTHS_ABBREVIATIONS` from download_utilities

**Dataclasses** for intermediate data:
- A showtime container (movie name, URL, date, time, format/label)
- See `MAMMShowtime` in mamm_download_task.py

**Two-Class Architecture** (follow mamm_download_task.py pattern):

1. **ScraperAndHTMLParser class** — Stateless with static methods:
   - `download_*()` — Fetch HTML using `fetch_page_html()`
   - `parse_*()` — Extract data from HTML using BeautifulSoup
   - Date parsing helpers

2. **ShowtimeSaver class** — Coordinates and persists:
   - Constructor takes scraper, TMDBService, and SupabaseStorageService
   - `execute()` — Main entry point returning `TaskReport`
   - `_process_movies()` — Lookup/create movies via `MovieLookupService`
   - `_save_showtimes()` — Per-date atomic transactions

**Movie Lookup:**
- Use `MovieSourceUrl.get_movie_for_source_url()` to check for existing movies
- Use `MovieLookupService` for TMDB matching

**Showtime Saving:**
- Use `@transaction.atomic` on the per-date save method
- Delete existing showtimes for the date before inserting new ones

**Celery Task:**
- Instantiate scraper, TMDBService, and SupabaseStorageService
- Create ShowtimeSaver with dependencies
- Call `saver.execute()` and print report
- Log failures to `OperationalIssue`

### 4. Create Management Command

Create `movies_app/management/commands/{source}_download.py` for manual testing.

Support `--theater <slug>` argument for single-theater testing.

See [colombia_com_run_download_task.py](../movies_app/management/commands/colombia_com_run_download_task.py) for reference.

### 5. Add Tests

Create `movies_app/tasks/tests/test_{source}_download_task.py`.

**Key testing requirements:**

- Save HTML snapshots in `html_snapshot/` directory for deterministic tests
- Mock `_fetch_html` or `fetch_page_html` to prevent real HTTP requests
- Mock `TMDBService` and `SupabaseStorageService` to prevent API calls
- Test year boundary logic if parsing dates without years (Dec→Jan transitions)
- Test the delete+insert behavior to verify old showtimes are replaced

See [test_mamm_download_task.py](../movies_app/tasks/tests/test_mamm_download_task.py) for examples.

Add auto-mock fixtures to [conftest.py](../movies_app/tasks/tests/conftest.py) for your scraper.

### 6. Add Theater Data

Add theaters to `seed_data/theaters.json` with the source URL field populated.

## Key Patterns

### Two-Phase Processing

Scrapers process data in two distinct phases to avoid holding database transactions open during API calls:

**Phase 1: Movie Processing (no transaction)**
- Extract unique movies from the scraped showtimes
- For each movie, check if it already exists via `MovieSourceUrl`
- If not, call TMDB API to search/match and create the Movie record
- Build a cache mapping movie URLs/titles to Movie objects

**Phase 2: Showtime Saving (per-date atomic transactions)**
- For each date, delete existing showtimes then insert new ones
- Use the pre-built movie cache—no API calls in this phase
- Each date is wrapped in `@transaction.atomic`

This separation ensures:
- API calls don't hold database locks
- If a transaction fails, only that date is affected
- Partial progress is preserved if the task crashes

### Per-Date Atomic Transactions

Don't wrap the entire task in a transaction. Instead, make each date's delete+insert atomic:

- If the task fails after 3 of 7 dates, those 3 dates are saved
- If insertion fails, the delete is rolled back
- Avoids long-running transactions

The outer `save_showtimes_from_html` function is NOT atomic; the inner `_save_showtimes_for_date` function IS atomic.

### Year Boundary Handling

When parsing dates without years (e.g., "3 Ene"), adjust the year based on proximity to today:

- If today is late December and the parsed date is early January → use next year
- If today is early January and the parsed date is late December → use previous year

See `_parse_date_string` in mamm_download_task.py for implementation.

### TMDB Matching

For best results, extract as much metadata as possible from the HTML page of the movie:

- `original_title` — Critical for non-English films
- `director` — Strong matching signal
- `release_year` — Filters results by year
- `actors` — Secondary matching signal

The `MovieLookupService` uses `metadata.original_title` for TMDB searches when available.

## Checklist

- [ ] Added `ScraperType` to enum
- [ ] Created task file following existing patterns
- [ ] Created management command
- [ ] Added tests with HTML snapshots
- [ ] Added mock fixtures to conftest.py
- [ ] Added theaters to seed_data/theaters.json
- [ ] Tested manually: `python manage.py {source}_download --theater <slug>`
- [ ] Ran `ruff check .`, `pyright`, `pytest`

## Common Issues

**Showtimes not being saved:** Check that `_extract_showtimes_from_html` returns valid data. Verify HTML selectors match current site structure.

**TMDB matches wrong movie:** Extract more metadata (director, actors, release_date). Check if original_title is being extracted correctly.

**Browser timeouts:** Increase timeout, add explicit waits after interactions, check for anti-bot measures.

**Transaction failures:** Check for unique constraint violations. Ensure delete happens before insert within the atomic block.
