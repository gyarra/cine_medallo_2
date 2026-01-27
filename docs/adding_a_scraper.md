# Adding a New Showtime Scraper

This guide explains how to add a scraper for a new movie theater website.

The key responsibilities of a scraper are:
- Save all showtimes for the group of theaters on the website being scraped
- Save any new movies encountered


## Reference Implementation

**Copy [cineprox_download_task.py](../movies_app/tasks/cineprox_download_task.py)** as your starting point. It demonstrates the recommended Template Method pattern with:

- `CineproxScraperAndHTMLParser` — Stateless class with static methods for I/O and HTML parsing
- `CineproxShowtimeSaver` — Extends `MovieAndShowtimeSaverTemplate` with scraper-specific logic

The template base class handles all the boilerplate:
- Theater iteration with error handling
- Movie deduplication across theaters
- TMDB lookup and movie creation
- Atomic showtime saving
- Task report generation

Also see:
- **[movie_and_showtime_saver_template.py](../movies_app/tasks/movie_and_showtime_saver_template.py)** — The abstract base class defining the template
- **[download_utilities.py](../movies_app/tasks/download_utilities.py)** — Shared utilities (`parse_time_string`, `fetch_page_html`, `MovieMetadata`, `TaskReport`, `BOGOTA_TZ`, `SPANISH_MONTHS_ABBREVIATIONS`)
- **[mamm_download_task.py](../movies_app/tasks/mamm_download_task.py)** — Simpler scraper (single theater, doesn't use template yet)
- **[colombia_com_download_task.py](../movies_app/tasks/colombia_com_download_task.py)** — Older multi-theater scraper (more complex, doesn't use template)

## Architecture Overview

### Template Method Pattern

New scrapers should extend `MovieAndShowtimeSaverTemplate` which provides:

```
execute()                           # Main entry point (template method)
├── For each theater:
│   ├── _find_movies()              # Abstract: scraper implements
│   ├── _get_or_create_movies()     # Template: handles TMDB lookup, caching
│   └── _process_showtimes_for_theater()  # Abstract: scraper implements
└── Return TaskReport
```

Your scraper only needs to implement three abstract methods:
1. `_find_movies(theater)` — Return list of `MovieInfo` from cartelera page
2. `_get_movie_metadata(movie_info)` — Fetch metadata from movie detail page
3. `_process_showtimes_for_theater(theater, movies_for_theater, movies_cache)` — Scrape and save showtimes

### Two-Class Architecture

Each scraper has two classes:

1. **ScraperAndHTMLParser** — Stateless with static methods:
   - `download_*()` — Fetch HTML using `fetch_page_html()`
   - `parse_*()` — Extract data from HTML using BeautifulSoup
   - Date/URL generation helpers

2. **ShowtimeSaver** (extends `MovieAndShowtimeSaverTemplate`):
   - Implements the three abstract methods
   - Uses the scraper class for all I/O and parsing
   - Calls `_save_showtimes_for_theater()` from template to persist data

## Implementation Steps

### 1. Add Scraper Type

Add an entry to `MovieSourceUrl.ScraperType` in [movie_source_url.py](../movies_app/models/movie_source_url.py).

### 2. Add Theater URL Field (if needed)

If theaters need a source-specific URL field, add it to the `Theater` model. Otherwise, use the existing `download_source_url` field.

### 3. Create the Task File

Create `movies_app/tasks/{source}_download_task.py` following the Cineprox pattern:

**Constants:**
```python
SOURCE_NAME = "your_source"
TASK_NAME = "your_source_download_task"
```

**Dataclasses** for intermediate data (movie cards, showtimes, metadata).

**ScraperAndHTMLParser class** — All static methods:
```python
class YourSourceScraperAndHTMLParser:
    @staticmethod
    def download_cartelera_html(url: str) -> str:
        return fetch_page_html(url, wait_selector="...", sleep_seconds_after_wait=1)

    @staticmethod
    def parse_movies_from_cartelera_html(html_content: str) -> list[YourMovieCard]:
        # BeautifulSoup parsing
        ...

    @staticmethod
    def parse_showtimes_from_detail_html(html_content: str, ...) -> list[YourShowtime]:
        ...
```

**ShowtimeSaver class** — Extends template:
```python
class YourSourceShowtimeSaver(MovieAndShowtimeSaverTemplate):
    def __init__(self, scraper, tmdb_service, storage_service):
        super().__init__(
            tmdb_service=tmdb_service,
            storage_service=storage_service,
            source_name=SOURCE_NAME,
            scraper_type="your_source",
            scraper_type_enum=MovieSourceUrl.ScraperType.YOUR_SOURCE,
            task_name=TASK_NAME,
        )
        self.scraper = scraper

    def _find_movies(self, theater: Theater) -> list[MovieInfo]:
        # Download cartelera, parse movies, return MovieInfo list
        ...

    def _get_movie_metadata(self, movie_info: MovieInfo) -> MovieMetadata | None:
        # Download detail page, extract metadata
        ...

    def _process_showtimes_for_theater(
        self,
        theater: Theater,
        movies_for_theater: list[MovieInfo],
        movies_cache: dict[str, Movie | None],
    ) -> int:
        # Scrape showtimes, build ShowtimeData list
        # Call self._save_showtimes_for_theater(theater, showtimes)
        ...
```

**Celery Task:**
```python
@app.task
def your_source_download_task():
    scraper = YourSourceScraperAndHTMLParser()
    tmdb_service = TMDBService()
    storage_service = SupabaseStorageService.create_from_settings()
    
    saver = YourSourceShowtimeSaver(scraper, tmdb_service, storage_service)
    report = saver.execute()
    report.print_report()
    return report
```

### 4. Create Management Command

Create `movies_app/management/commands/{source}_download.py` for manual testing.

See [cineprox_download.py](../movies_app/management/commands/cineprox_download.py) for reference.

### 5. Add Tests

Create `movies_app/tasks/tests/test_{source}_download_task.py`.

**Key testing requirements:**

- Save HTML snapshots in `html_snapshot/` directory for deterministic tests
- Mock `fetch_page_html` to return snapshot HTML
- Mock `TMDBService` and `SupabaseStorageService` to prevent API calls
- Test year boundary logic if parsing dates without years
- Test the delete+insert behavior to verify old showtimes are replaced
- Test error handling (missing movies, malformed HTML)

See [test_cineprox_download_task.py](../movies_app/tasks/tests/test_cineprox_download_task.py) for comprehensive examples.

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
