# Adding a New Showtime Scraper

This guide explains how to add a scraper for a new movie theater website, following the same architecture as the `colombia_com_download_task.py` implementation.

## Overview

The scraper system follows a consistent pattern:

1. **Celery Task** - Entry point, iterates theaters, handles errors
2. **Theater Processing** - Scrapes all dates for a theater in a transaction
3. **Date Processing** - Extracts movies and showtimes for a specific date
4. **Movie Lookup** - Matches scraped movies to TMDB, creates Movie records
5. **Showtime Creation** - Saves individual showtimes to the database

## Prerequisites

Before starting, ensure you have:

- [ ] A `ScraperType` entry in `MovieSourceUrl.ScraperType` enum
- [ ] A URL field on the `Theater` model (or use `download_source_url`)
- [ ] Understanding of the target website's HTML structure

## Step 1: Add Scraper Type

Edit `movies_app/models/movie_source_url.py`:

```python
class ScraperType(models.TextChoices):
    COLOMBIA_COM = "colombia_com", "colombia.com"
    MAMM = "mamm", "MAMM (elmamm.org)"
    CINE_COLOMBIA = "cine_colombia", "Cine Colombia"  # Add your new scraper
    # ... etc
```

## Step 2: Create the Task File

Create a new file in `movies_app/tasks/` named `{source}_download_task.py`.

### Required Imports

```python
from __future__ import annotations

import asyncio
import datetime
import logging
import re
import traceback
import zoneinfo
from dataclasses import dataclass

from bs4 import BeautifulSoup
from django.db import transaction
from camoufox.async_api import AsyncCamoufox

from config.celery_app import app
from movies_app.models import MovieSourceUrl, OperationalIssue, Showtime, Theater, UnfindableMovieUrl
from movies_app.services.tmdb_service import TMDBService
from movies_app.services.movie_lookup_result import MovieLookupResult
from movies_app.tasks.download_utilities import MovieMetadata, TaskReport
from movies_app.services.movie_lookup_service import MovieLookupService

logger = logging.getLogger(__name__)
```

### Required Constants

```python
# Browser configuration
BROWSER_TIMEOUT_SECONDS = 120

# Timezone for the region
LOCAL_TZ = zoneinfo.ZoneInfo("America/Bogota")

# Source name for logging and error tracking
SOURCE_NAME = "your_source.com"

# Your scraper type from the enum
SCRAPER_TYPE = MovieSourceUrl.ScraperType.YOUR_SCRAPER
```

## Step 3: Define Data Classes

These dataclasses capture the structure of extracted showtime data:

```python
@dataclass
class ShowtimeDescription:
    """A showtime format with its associated times."""
    description: str  # e.g., "2D Subtitulada", "3D Doblada"
    start_times: list[datetime.time]


@dataclass
class MovieShowtimes:
    """All showtimes for a single movie at a theater."""
    movie_name: str
    movie_url: str | None  # URL to movie detail page (for metadata scraping)
    descriptions: list[ShowtimeDescription]
```

## Step 4: Implement HTML Parsing Functions

### Time Parser

Adapt to your source's time format:

```python
def _parse_time_string(time_str: str) -> datetime.time | None:
    """Parse time string to datetime.time.

    Adapt this to match your source's format:
    - "12:50 pm" -> 12:50
    - "16:30" -> 16:30
    - "4:30 PM" -> 16:30
    """
    time_str = time_str.strip().lower()

    # Example: 12-hour format with am/pm
    match = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm)", time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        period = match.group(3)

        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0

        return datetime.time(hour, minute)

    return None
```

### Showtime Extractor

Parse the theater page HTML to extract movie showtimes:

```python
def _extract_showtimes_from_html(html_content: str) -> list[MovieShowtimes]:
    """Extract movie showtimes from theater page HTML.

    This is the most site-specific function. You need to:
    1. Find all movie containers in the HTML
    2. Extract movie name and URL for each
    3. Extract all showtimes grouped by format/description
    """
    soup = BeautifulSoup(html_content, "lxml")
    result: list[MovieShowtimes] = []

    # Find all movie containers (adapt selector to your HTML)
    movie_containers = soup.find_all("div", class_="movie-item")

    for container in movie_containers:
        # Extract movie name
        name_elem = container.find("h3", class_="movie-title")
        if not name_elem:
            continue
        movie_name = name_elem.get_text(strip=True)

        # Extract movie URL (for metadata scraping)
        link = container.find("a", href=True)
        movie_url = link["href"] if link else None

        # Extract showtimes grouped by format
        descriptions: list[ShowtimeDescription] = []

        format_blocks = container.find_all("div", class_="format-block")
        for block in format_blocks:
            format_name = block.find("span", class_="format-name")
            description = format_name.get_text(strip=True) if format_name else ""

            times: list[datetime.time] = []
            time_items = block.find_all("span", class_="showtime")
            for item in time_items:
                parsed_time = _parse_time_string(item.get_text())
                if parsed_time:
                    times.append(parsed_time)

            if times:
                descriptions.append(ShowtimeDescription(
                    description=description,
                    start_times=times,
                ))

        if descriptions:
            result.append(MovieShowtimes(
                movie_name=movie_name,
                movie_url=movie_url,
                descriptions=descriptions,
            ))

    return result
```

### Date Options Extractor (if applicable)

If the site has a date selector:

```python
def _find_date_options(html_content: str) -> list[datetime.date]:
    """Extract available date options from page.

    Many sites have date dropdowns or tabs. Extract all available dates.
    """
    soup = BeautifulSoup(html_content, "lxml")
    dates: list[datetime.date] = []

    # Example: date dropdown
    select = soup.find("select", {"name": "date"})
    if select:
        for option in select.find_all("option"):
            value = option.get("value")
            if value:
                try:
                    # Adapt date format to your source
                    parsed = datetime.datetime.strptime(value, "%Y-%m-%d").date()
                    dates.append(parsed)
                except ValueError:
                    logger.warning(f"Could not parse date: {value}")

    return dates
```

### Movie Metadata Extractor

Extract metadata from movie detail pages for better TMDB matching:

```python
def _extract_movie_metadata_from_html(html_content: str) -> MovieMetadata | None:
    """Extract movie metadata from detail page.

    The more metadata you extract, the better TMDB matching will be:
    - original_title: Critical for non-English films
    - release_date/release_year: Helps filter TMDB results
    - director: Strong matching signal (+150 points)
    - actors: Good matching signal (+30 per actor)
    """
    soup = BeautifulSoup(html_content, "lxml")

    # Initialize with defaults
    genre = ""
    duration_minutes: int | None = None
    classification = ""
    director = ""
    actors: list[str] = []
    original_title: str | None = None
    release_date: datetime.date | None = None
    release_year: int | None = None

    # Extract each field based on your HTML structure
    # ... (site-specific parsing)

    return MovieMetadata(
        genre=genre,
        duration_minutes=duration_minutes,
        classification=classification,
        director=director,
        actors=actors,
        original_title=original_title,
        release_date=release_date,
        release_year=release_year,
    )
```

## Step 5: Implement Browser Scraping Functions

### Theater Page Scraper

```python
async def _scrape_theater_html_async(
    theater: Theater,
    target_date: datetime.date | None,
) -> str:
    """Fetch HTML from theater page using headless browser.

    Uses Camoufox for JavaScript-rendered content and anti-bot evasion.
    """
    url = theater.your_source_url  # Adapt field name
    if not url:
        raise ValueError(f"Theater '{theater.name}' has no source URL")

    logger.info(f"Scraping showtimes for: {theater.name}")
    logger.info(f"URL: {url}")

    async with AsyncCamoufox(headless=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=BROWSER_TIMEOUT_SECONDS * 1000,
            )

            # If date selection is needed
            if target_date:
                # Adapt to your site's date selection mechanism
                date_str = target_date.strftime("%Y-%m-%d")
                await page.click(f'[data-date="{date_str}"]')
                await page.wait_for_load_state("networkidle")
                await asyncio.sleep(2.0)  # Wait for content update

            html_content = await page.content()
        finally:
            await context.close()

    return html_content
```

### Movie Page Scraper (optional)

If your source has separate movie detail pages:

```python
async def _scrape_movie_page_async(movie_url: str) -> str:
    """Fetch HTML from movie detail page."""
    logger.info(f"Scraping movie page: {movie_url}")

    async with AsyncCamoufox(headless=True) as browser:
        context = await browser.new_context()
        page = await context.new_page()

        try:
            await page.goto(
                movie_url,
                wait_until="domcontentloaded",
                timeout=BROWSER_TIMEOUT_SECONDS * 1000,
            )
            html_content = await page.content()
        finally:
            await context.close()

    return html_content
```

## Step 6: Implement Movie Lookup

This function wraps the generic `MovieLookupService` with source-specific logic:

```python
def _get_or_create_movie(
    movie_name: str,
    movie_url: str | None,
    tmdb_service: TMDBService,
    storage_service,
) -> MovieLookupResult:
    """Get or create a movie from this source's listing.

    Flow:
    1. Check if movie already exists by URL (skip scraping)
    2. Check if URL is known unfindable (skip processing)
    3. Scrape metadata from movie detail page
    4. Use MovieLookupService for TMDB matching
    5. Apply source-specific post-processing (e.g., age ratings)
    """
    lookup_service = MovieLookupService(tmdb_service, storage_service, SOURCE_NAME)

    # Step 1: Check for existing movie by URL
    if movie_url:
        existing = MovieSourceUrl.objects.filter(
            scraper_type=SCRAPER_TYPE,
            url=movie_url,
        ).select_related("movie").first()
        if existing:
            return MovieLookupResult(movie=existing.movie, is_new=False, tmdb_called=False)

        # Step 2: Check if known unfindable
        unfindable = UnfindableMovieUrl.objects.filter(url=movie_url).first()
        if unfindable:
            unfindable.attempts += 1
            unfindable.save(update_fields=["attempts", "last_seen"])
            return MovieLookupResult(movie=None, is_new=False, tmdb_called=False)

    # Step 3: Scrape metadata
    metadata: MovieMetadata | None = None
    if movie_url:
        try:
            html = asyncio.run(_scrape_movie_page_async(movie_url))
            metadata = _extract_movie_metadata_from_html(html)
        except Exception as e:
            logger.warning(f"Failed to scrape movie page: {e}")
            # Record but continue - TMDB lookup may still work
            lookup_service.record_unfindable_url(
                movie_url, movie_name, None, UnfindableMovieUrl.Reason.NO_METADATA
            )

    # Step 4: Use generic lookup service
    result = lookup_service.get_or_create_movie(
        movie_name=movie_name,
        source_url=movie_url,
        scraper_type=SCRAPER_TYPE,
        metadata=metadata,
    )

    # Step 5: Source-specific post-processing
    if result.movie and result.is_new and metadata:
        # Example: Set age rating from scraped classification
        if metadata.classification and not result.movie.age_rating_colombia:
            result.movie.age_rating_colombia = metadata.classification
            result.movie.save(update_fields=["age_rating_colombia"])

    return result
```

## Step 7: Implement Theater Processing

```python
@transaction.atomic
def save_showtimes_for_theater(theater: Theater) -> TaskReport:
    """Scrape and save all showtimes for a theater.

    Uses @transaction.atomic to ensure all-or-nothing saves.
    """
    # Initial scrape (today's page)
    html_content = asyncio.run(_scrape_theater_html_async(theater, target_date=None))

    # Get available dates
    date_options = _find_date_options(html_content)
    if not date_options:
        # Single-date source: just process the current page
        date_options = [datetime.datetime.now(LOCAL_TZ).date()]

    # Initialize services
    tmdb_service = TMDBService()
    lookup_service = MovieLookupService(tmdb_service, None, SOURCE_NAME)
    storage_service = lookup_service.create_storage_service()

    # Process each date
    total_showtimes = 0
    total_tmdb_calls = 0
    all_new_movies: list[str] = []
    today = datetime.datetime.now(LOCAL_TZ).date()

    for target_date in date_options:
        # Reuse initial HTML for today, scrape fresh for other dates
        if target_date == today:
            report = _save_showtimes_for_date(
                theater, None, tmdb_service, storage_service, html_content
            )
        else:
            report = _save_showtimes_for_date(
                theater, target_date, tmdb_service, storage_service, None
            )

        total_showtimes += report.total_showtimes
        total_tmdb_calls += report.tmdb_calls
        all_new_movies.extend(m for m in report.new_movies if m not in all_new_movies)

    return TaskReport(
        total_showtimes=total_showtimes,
        tmdb_calls=total_tmdb_calls,
        new_movies=all_new_movies,
    )


def _save_showtimes_for_date(
    theater: Theater,
    target_date: datetime.date | None,
    tmdb_service: TMDBService,
    storage_service,
    html_content: str | None,
) -> TaskReport:
    """Process showtimes for a specific date."""
    if not html_content:
        html_content = asyncio.run(_scrape_theater_html_async(theater, target_date))

    movie_showtimes_list = _extract_showtimes_from_html(html_content)
    effective_date = target_date or datetime.datetime.now(LOCAL_TZ).date()

    if not movie_showtimes_list:
        logger.warning(f"No showtimes found for {theater.name} on {effective_date}")
        return TaskReport(total_showtimes=0, tmdb_calls=0, new_movies=[])

    # Delete existing showtimes for this theater+date
    Showtime.objects.filter(theater=theater, start_date=effective_date).delete()

    showtimes_saved = 0
    tmdb_calls = 0
    new_movies: list[str] = []

    for movie_showtime in movie_showtimes_list:
        lookup_result = _get_or_create_movie(
            movie_name=movie_showtime.movie_name,
            movie_url=movie_showtime.movie_url,
            tmdb_service=tmdb_service,
            storage_service=storage_service,
        )

        if lookup_result.tmdb_called:
            tmdb_calls += 1
        if lookup_result.is_new and lookup_result.movie:
            new_movies.append(str(lookup_result.movie))
        if not lookup_result.movie:
            continue  # Skip movies we couldn't match

        # Create showtimes
        for desc in movie_showtime.descriptions:
            for start_time in desc.start_times:
                Showtime.objects.create(
                    theater=theater,
                    movie=lookup_result.movie,
                    start_date=effective_date,
                    start_time=start_time,
                    format=desc.description,
                    source_url=theater.your_source_url,  # Adapt field
                )
                showtimes_saved += 1

    logger.info(f"Saved {showtimes_saved} showtimes for {theater.name} on {effective_date}")
    return TaskReport(
        total_showtimes=showtimes_saved,
        tmdb_calls=tmdb_calls,
        new_movies=new_movies,
    )
```

## Step 8: Create the Celery Task

```python
@app.task
def your_source_download_task():
    """Celery task to download showtimes from your source.

    Iterates through all theaters with the appropriate URL field,
    scrapes showtimes, matches to TMDB, and saves to database.
    """
    logger.info(f"Starting {SOURCE_NAME} download task")

    # Query theaters with this source's URL
    theaters = Theater.objects.exclude(
        your_source_url__isnull=True
    ).exclude(your_source_url="")

    if not theaters.exists():
        logger.warning(f"No theaters found with {SOURCE_NAME} URL")
        return

    logger.info(f"Found {theaters.count()} theaters")

    total_showtimes = 0
    total_tmdb_calls = 0
    all_new_movies: list[str] = []
    failed_theaters: list[str] = []

    for theater in theaters:
        try:
            report = save_showtimes_for_theater(theater)
            total_showtimes += report.total_showtimes
            total_tmdb_calls += report.tmdb_calls
            all_new_movies.extend(m for m in report.new_movies if m not in all_new_movies)
        except Exception as e:
            logger.error(f"Failed to process {theater.name}: {e}")
            OperationalIssue.objects.create(
                name="Theater Processing Failed",
                task=f"{SOURCE_NAME}_download_task",
                error_message=str(e),
                traceback=traceback.format_exc(),
                context={"theater_name": theater.name},
                severity=OperationalIssue.Severity.ERROR,
            )
            failed_theaters.append(theater.name)

    # Print final report
    TaskReport(
        total_showtimes=total_showtimes,
        tmdb_calls=total_tmdb_calls,
        new_movies=all_new_movies,
    ).print_report()

    if failed_theaters:
        logger.warning(f"Failed theaters: {failed_theaters}")
```

## Step 9: Add Management Command

Create `movies_app/management/commands/{source}_download.py`:

```python
"""
{Source} Download Command

Downloads movie showtime data from {source}.

Usage:
    python manage.py {source}_download
    python manage.py {source}_download --theater <slug>
"""

from django.core.management.base import BaseCommand
from movies_app.models import Theater
from movies_app.tasks.{source}_download_task import (
    save_showtimes_for_theater,
    {source}_download_task,
)


class Command(BaseCommand):
    help = "Download showtimes from {source}"

    def add_arguments(self, parser):
        parser.add_argument(
            "--theater",
            type=str,
            help="Process only this theater (by slug)",
        )

    def handle(self, *args, **options):
        theater_slug = options.get("theater")

        if theater_slug:
            try:
                theater = Theater.objects.get(slug=theater_slug)
                report = save_showtimes_for_theater(theater)
                self.stdout.write(f"Saved {report.total_showtimes} showtimes")
            except Theater.DoesNotExist:
                self.stderr.write(f"Theater not found: {theater_slug}")
        else:
            {source}_download_task()
```

## Step 10: Add Tests

Create `movies_app/tasks/tests/test_{source}_download_task.py`:

### Key Testing Principles

1. **Mock external HTTP requests** — Never hit real websites in tests. Use HTML snapshots and mock `_fetch_html` or browser functions.

2. **Mock database-dependent services** — Services like `TMDBService` and `SupabaseStorageService` should be mocked to prevent real API calls. Use fixtures in `conftest.py`.

3. **Test year boundary cases** — When parsing dates without years (e.g., "3 Ene"), test the edge case where today is late December and the schedule contains early January dates (or vice versa).

### Example Test Structure

```python
import datetime
import pytest
from unittest.mock import patch

from movies_app.tasks.{source}_download_task import (
    _parse_time_string,
    _extract_showtimes_from_html,
    _extract_movie_metadata_from_html,
    BOGOTA_TZ,  # or your timezone constant
)


class TestTimeParser:
    def test_parse_valid_time(self):
        assert _parse_time_string("2:30 pm") == datetime.time(14, 30)
        assert _parse_time_string("12:00 am") == datetime.time(0, 0)

    def test_parse_invalid_time(self):
        assert _parse_time_string("invalid") is None


class TestShowtimeExtraction:
    def test_extract_from_sample_html(self):
        with open("movies_app/tasks/tests/html_snapshot/{source}_sample.html") as f:
            html = f.read()

        result = _extract_showtimes_from_html(html)

        assert len(result) > 0
        assert result[0].movie_name
        assert len(result[0].descriptions) > 0
```

### Testing Year Boundary Logic

When dates don't include a year, the scraper infers the year from today's date. Test both directions:

```python
def _make_schedule_html(day_text: str) -> str:
    """Create minimal HTML for testing date parsing."""
    return f"""
    <section class="schedule">
        <div class="day">{day_text}</div>
        <div class="movie">
            <h3>Test Movie</h3>
            <span class="time">7:00 pm</span>
        </div>
    </section>
    """


class TestYearBoundaryAdjustment:
    def test_adjusts_year_forward_when_in_late_december(self):
        """When today is Dec 30 and we parse 'Jan 2', year should be next year."""
        mock_now = datetime.datetime(2025, 12, 30, 12, 0, 0, tzinfo=BOGOTA_TZ)
        html = _make_schedule_html("viernes 2 Ene")

        with patch("movies_app.tasks.{source}_download_task.datetime") as mock_datetime:
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date
            mock_datetime.time = datetime.time

            showtimes = _extract_showtimes_from_html(html)

        assert len(showtimes) == 1
        # Should be 2026, not 2025
        assert showtimes[0].date == datetime.date(2026, 1, 2)

    def test_adjusts_year_backward_when_in_early_january(self):
        """When today is Jan 2 and we parse 'Dec 30', year should be previous year."""
        mock_now = datetime.datetime(2026, 1, 2, 12, 0, 0, tzinfo=BOGOTA_TZ)
        html = _make_schedule_html("martes 30 Dic")

        with patch("movies_app.tasks.{source}_download_task.datetime") as mock_datetime:
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date
            mock_datetime.time = datetime.time

            showtimes = _extract_showtimes_from_html(html)

        assert len(showtimes) == 1
        # Should be 2025, not 2026
        assert showtimes[0].date == datetime.date(2025, 12, 30)
```

### Auto-mocking External Services in conftest.py

Add fixtures to `movies_app/tasks/tests/conftest.py` to automatically mock external dependencies:

```python
@pytest.fixture(autouse=True)
def mock_fetch_html():
    """Prevent real HTTP requests during tests."""
    mock_html = "<html><body>Mocked content</body></html>"
    with patch("movies_app.tasks.{source}_download_task._fetch_html", return_value=mock_html):
        yield


@pytest.fixture(autouse=True)
def mock_tmdb_service():
    """Prevent real TMDB API calls during tests."""
    with patch("movies_app.tasks.{source}_download_task.TMDBService") as mock:
        mock_instance = MagicMock()
        mock_instance.search_movie.return_value = TMDBSearchResponse(...)
        mock.return_value = mock_instance
        yield mock_instance
```

### Integration Tests with Database

```python
@pytest.mark.django_db
class TestSaveShowtimes:
    def test_saves_showtimes_from_html(self, your_theater_fixture):
        """Test full flow from HTML to database."""
        with open("movies_app/tasks/tests/html_snapshot/{source}_sample.html") as f:
            html = f.read()

        report = save_showtimes_from_html(html)

        assert report.total_showtimes > 0
        assert Showtime.objects.filter(theater=your_theater_fixture).exists()
```

### HTML Snapshots

Save real HTML samples for testing in `movies_app/tasks/tests/html_snapshot/`:
- `{source}_theater_page.html` — Theater showtime listing
- `{source}_movie_detail.html` — Movie metadata page (if scraped)

## Checklist

- [ ] Added `ScraperType` to enum
- [ ] Created task file with all required functions
- [ ] Implemented HTML parsing for your source
- [ ] Created management command
- [ ] Added tests with HTML snapshots
- [ ] Added theaters to `seed_data/theaters.json` with source URL
- [ ] Tested manually with `python manage.py {source}_download --theater <slug>`
- [ ] Ran `ruff check .`, `pyright`, `pytest`

## TMDB Matching Tips

For best TMDB matching results:

1. **Extract original_title**: Critical for non-English films. Often in parentheses after the Spanish title.

2. **Extract release_date**: Enables exact date matching (instant return) or year scoring.

3. **Extract director**: Worth +150 points in matching. Very reliable signal.

4. **Extract actors**: Worth +30 each (max 90). Good secondary signal.

5. **Prefer original_title for search**: The `MovieLookupService` will use `metadata.original_title` if available, which typically yields better TMDB results than Spanish titles.

## Common Issues

### Showtimes not being saved
- Check if `_extract_showtimes_from_html` returns valid data
- Verify HTML selectors match current site structure
- Check if movie lookup is returning `None`

### TMDB matches wrong movie
- Extract more metadata (director, actors, release_date)
- Check if original_title is being extracted correctly
- Review TMDB search results in logs

### Browser timeouts
- Increase `BROWSER_TIMEOUT_SECONDS`
- Add explicit waits after interactions
- Check if site has anti-bot measures

### Transaction failures
- Check for unique constraint violations
- Ensure all database writes are within the atomic block
- Consider adding retry logic
