"""
Download From Colombia.com Task

Celery task for scraping movie showtime data from colombia.com.
"""

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
from movies_app.models import Movie, OperationalIssue, Showtime, Theater, UnfindableMovieUrl
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.download_utilities import (
    MovieLookupResult,
    MovieMetadata,
    TaskReport,
    create_storage_service,
    get_or_create_movie,
    record_unfindable_url,
)

logger = logging.getLogger(__name__)

# Browser configuration
BROWSER_TIMEOUT_SECONDS = 120

# Colombia timezone
BOGOTA_TZ = zoneinfo.ZoneInfo("America/Bogota")

# Base URL for colombia.com
COLOMBIA_COM_BASE_URL = "https://www.colombia.com"

# Source name for logging
SOURCE_NAME = "colombia.com"


@dataclass
class ShowtimeDescription:
    description: str
    start_times: list[datetime.time]


@dataclass
class MovieShowtimes:
    movie_name: str
    movie_url: str | None
    descriptions: list[ShowtimeDescription]


def _parse_time_string(time_str: str) -> datetime.time | None:
    """Parse time string like '12:50 pm' or '4:30 pm' to datetime.time."""
    time_str = time_str.strip().lower()
    match = re.match(r"(\d{1,2}):(\d{2})\s*(am|pm)", time_str)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    period = match.group(3)

    if period == "pm" and hour != 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0

    return datetime.time(hour, minute)


def _extract_showtimes_from_html(html_content: str) -> list[MovieShowtimes]:
    """
    Extract movie showtimes from colombia.com theater page HTML.

    Returns a list of MovieShowtimes, each containing the movie name,
    URL to the movie detail page, and a list of ShowtimeDescription objects.
    """
    soup = BeautifulSoup(html_content, "lxml")
    movie_boxes = soup.find_all("div", class_="caja-cinema")

    result: list[MovieShowtimes] = []

    for box in movie_boxes:
        name_div = box.find("div", class_="nombre-pelicula")
        if not name_div:
            continue

        anchor = name_div.find("a")
        if not anchor:
            continue

        movie_name = " ".join(anchor.get_text().split())
        if not movie_name:
            continue

        movie_url: str | None = None
        href = anchor.get("href")
        if href and isinstance(href, str):
            if href.startswith("http"):
                movie_url = href
            elif href.startswith("/"):
                movie_url = f"{COLOMBIA_COM_BASE_URL}{href}"

        descriptions: list[ShowtimeDescription] = []

        info_divs = box.find_all("div", class_="info-pelicula")
        for info_div in info_divs:
            format_div = info_div.find("div", class_="formato-pelicula")
            description = ""
            if format_div:
                description = format_div.get_text(strip=True)

            times_div = info_div.find("div", class_="horarios-funcion")
            start_times: list[datetime.time] = []
            if times_div:
                time_items = times_div.find_all("li")
                for li in time_items:
                    time_text = li.get_text(strip=True)
                    parsed_time = _parse_time_string(time_text)
                    if parsed_time:
                        start_times.append(parsed_time)

            if start_times:
                descriptions.append(
                    ShowtimeDescription(description=description, start_times=start_times)
                )

        if descriptions:
            result.append(MovieShowtimes(movie_name=movie_name, movie_url=movie_url, descriptions=descriptions))

    return result


def _find_date_options(html_content: str) -> list[datetime.date]:
    """Extract available date options from the colombia.com page dropdown."""
    soup = BeautifulSoup(html_content, "lxml")
    select = soup.find("select", {"name": "fecha"})
    if not select:
        return []

    dates: list[datetime.date] = []
    for option in select.find_all("option"):
        value = option.get("value")
        if value and isinstance(value, str):
            try:
                parsed = datetime.datetime.strptime(value, "%m/%d/%Y").date()
                dates.append(parsed)
            except ValueError:
                logger.warning(f"Could not parse date option: {value}")
                OperationalIssue.objects.create(
                    name="Date Option Parse Error",
                    task="_find_date_options",
                    error_message=f"Could not parse date option value: {value}",
                    context={"value": value},
                    severity=OperationalIssue.Severity.WARNING,
                )
    return dates


def _extract_movie_metadata_from_html(html_content: str) -> MovieMetadata | None:
    """
    Extract movie metadata from colombia.com individual movie page HTML.

    Parses: Género, Duración, Clasificación, Director, Actores, Fecha de estreno
    Also extracts original title from parentheses in movie title, e.g.,
    "La Empleada (The Housemaid)" -> original_title = "The Housemaid"
    """
    soup = BeautifulSoup(html_content, "lxml")

    genre = ""
    duration_minutes: int | None = None
    classification = ""
    director = ""
    actors: list[str] = []
    release_date = ""
    original_title: str | None = None

    # Find the movie info section (within class "pelicula")
    movie_div = soup.find("div", class_="pelicula")
    if not movie_div:
        return None

    # Extract original title from movie name if in parentheses
    # e.g., "La Empleada (The Housemaid)" -> "The Housemaid"
    title_h1 = soup.find("h1")
    if title_h1:
        title_text = title_h1.get_text(strip=True)
        paren_match = re.search(r"\(([^)]+)\)\s*$", title_text)
        if paren_match:
            original_title = paren_match.group(1).strip()

    # Extract each metadata field by finding <b> tags with specific text
    for div in movie_div.find_all("div"):
        text = div.get_text(strip=True)

        if text.startswith("Género:"):
            b_tag = div.find("b")
            if b_tag:
                genre = text.replace("Género:", "").strip()

        elif text.startswith("Duración:"):
            # Format: "85 minutos"
            duration_text = text.replace("Duración:", "").strip()
            duration_match = re.match(r"(\d+)", duration_text)
            if duration_match:
                duration_minutes = int(duration_match.group(1))

        elif text.startswith("Clasificación:"):
            classification = text.replace("Clasificación:", "").strip()

        elif text.startswith("Director:"):
            director = text.replace("Director:", "").strip()

        elif text.startswith("Actores:"):
            actors_text = text.replace("Actores:", "").strip()
            # Split by comma or "y" (Spanish "and")
            actors_raw = re.split(r",\s*|\s+y\s+", actors_text)
            actors = [a.strip() for a in actors_raw if a.strip()]

    # Look for release date which has a different format
    fecha_div = soup.find("div", class_="fecha-estreno")
    if fecha_div:
        fecha_text = fecha_div.get_text(strip=True)
        # Format: "Fecha de estreno: Ene 15 / 2026"
        if "Fecha de estreno:" in fecha_text:
            release_date = fecha_text.replace("Fecha de estreno:", "").strip()

    # Parse the release date into standardized format
    parsed_date = _parse_release_date_from_colombia_date(release_date)
    parsed_year = _parse_release_year_from_colombia_date(release_date)

    return MovieMetadata(
        genre=genre,
        duration_minutes=duration_minutes,
        classification=classification,
        director=director,
        actors=actors,
        original_title=original_title,
        release_date=parsed_date,
        release_year=parsed_year,
    )


def _parse_release_year_from_colombia_date(release_date_str: str) -> int | None:
    """
    Parse year from colombia.com release date format.

    Format examples: "Ene 15 / 2026", "Dic 25 / 2025"
    """
    if not release_date_str:
        return None

    # Look for 4-digit year at the end
    match = re.search(r"(\d{4})", release_date_str)
    if match:
        return int(match.group(1))
    return None


def _parse_release_date_from_colombia_date(release_date_str: str) -> datetime.date | None:
    """
    Parse full date from colombia.com release date format.

    Format examples: "Ene 15 / 2026", "Dic 25 / 2025"
    Returns datetime.date or None if parsing fails.
    """
    if not release_date_str:
        return None

    # Spanish month abbreviations to month numbers
    month_map = {
        "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
        "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
    }

    # Pattern: "Mes DD / YYYY" e.g., "Ene 15 / 2026"
    match = re.match(r"(\w{3})\s+(\d{1,2})\s*/\s*(\d{4})", release_date_str.strip(), re.IGNORECASE)
    if match:
        month_abbr = match.group(1).lower()
        day = int(match.group(2))
        year = int(match.group(3))

        month = month_map.get(month_abbr)
        if month:
            try:
                return datetime.date(year, month, day)
            except ValueError:
                pass

    return None


async def _scrape_movie_page_async(movie_url: str) -> str:
    """Fetch HTML content from a movie's colombia.com page."""
    logger.info(f"Scraping movie page: {movie_url}")

    browser_options = {
        "headless": True,
    }

    async with AsyncCamoufox(**browser_options) as browser:
        context = await browser.new_context()  # pyright: ignore[reportAttributeAccessIssue]
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


async def _scrape_theater_html_async(
    theater: Theater,
    target_date: datetime.date | None,
) -> str:
    """Fetch HTML content from a theater's colombia.com page."""
    if not theater.colombia_dot_com_url:
        raise ValueError(f"Theater '{theater.name}' has no colombia_dot_com_url")

    logger.info(f"Scraping showtimes for theater: {theater.name}")
    logger.info(f"URL: {theater.colombia_dot_com_url}")

    browser_options = {
        "headless": True,
    }

    async with AsyncCamoufox(**browser_options) as browser:
        context = await browser.new_context()  # pyright: ignore[reportAttributeAccessIssue]
        page = await context.new_page()

        try:
            await page.goto(
                theater.colombia_dot_com_url,
                wait_until="domcontentloaded",
                timeout=BROWSER_TIMEOUT_SECONDS * 1000,
            )

            if target_date:
                date_value = target_date.strftime("%m/%d/%Y").lstrip("0").replace("/0", "/")
                logger.info(f"Selecting date: {target_date} (value: {date_value})")

                wait_start = datetime.datetime.now()
                await page.select_option("select[name='fecha']", date_value)
                await page.wait_for_load_state("networkidle")

                # Sleep for 5 seconds while the conent updates.
                # We've tried a number of "more efficient" strategies, that are faster, however they don't work,
                # and we end up with incorrect showtimes. This works, so keep it, unless we find a better way that works.
                await asyncio.sleep(5.0)

                wait_duration = (datetime.datetime.now() - wait_start).total_seconds()
                logger.info(f"Content change wait took {wait_duration:.2f}s for date {target_date}")

            html_content = await page.content()
        finally:
            await context.close()
    logger.info(f"Finished scraping showtimes for theater: {theater.name}\n")

    return html_content


def _scrape_and_create_metadata(movie_url: str, movie_name: str) -> MovieMetadata | None:
    """
    Scrape metadata from a colombia.com movie page.

    Returns MovieMetadata or None if scraping fails.
    """
    try:
        movie_html = asyncio.run(_scrape_movie_page_async(movie_url))
        metadata = _extract_movie_metadata_from_html(movie_html)
        if metadata:
            logger.info(
                f"Scraped metadata for '{movie_name}': "
                f"genre={metadata.genre}, duration={metadata.duration_minutes}, "
                f"release_date={metadata.release_date}, director={metadata.director}, "
                f"original_title={metadata.original_title}"
            )
        return metadata
    except Exception as e:
        logger.warning(f"Failed to scrape movie page for '{movie_name}': {e}")
        OperationalIssue.objects.create(
            name="Movie Page Scrape Failed",
            task="_get_or_create_movie_colombia",
            error_message=f"Failed to scrape colombia.com movie page for '{movie_name}': {e}",
            traceback=traceback.format_exc(),
            context={"movie_name": movie_name, "movie_url": movie_url},
            severity=OperationalIssue.Severity.WARNING,
        )
        return None


def _get_or_create_movie_colombia(
    movie_name: str,
    movie_url: str | None,
    tmdb_service: TMDBService,
    storage_service,
) -> MovieLookupResult:
    """
    Get or create a movie from colombia.com listing.

    This wraps the generic get_or_create_movie with colombia.com-specific logic:
    1. Checks for existing movie by URL first
    2. Checks if URL is known to be unfindable
    3. Scrapes metadata from colombia.com movie page
    4. Uses classification as age_rating_colombia fallback
    """
    # Step 1: Check for existing movie by URL first (avoid scraping if we already have it)
    if movie_url:
        existing_movie = Movie.objects.filter(colombia_dot_com_url=movie_url).first()
        if existing_movie:
            return MovieLookupResult(movie=existing_movie, is_new=False, tmdb_called=False)

        # Step 1b: Check if this URL is already known to be unfindable
        unfindable = UnfindableMovieUrl.objects.filter(url=movie_url).first()
        if unfindable:
            unfindable.attempts += 1
            unfindable.save(update_fields=["attempts", "last_seen"])
            logger.debug(f"Skipping processing for known unfindable URL: {movie_url}")
            return MovieLookupResult(movie=None, is_new=False, tmdb_called=False)

    # Step 2: Scrape metadata from colombia.com movie page
    metadata: MovieMetadata | None = None
    if movie_url:
        metadata = _scrape_and_create_metadata(movie_url, movie_name)
        if metadata is None:
            # Record as unfindable due to metadata scrape failure
            record_unfindable_url(
                movie_url, movie_name, None, UnfindableMovieUrl.Reason.NO_METADATA, SOURCE_NAME
            )
            return MovieLookupResult(movie=None, is_new=False, tmdb_called=False)

    # Step 3: Use generic get_or_create_movie
    result = get_or_create_movie(
        movie_name=movie_name,
        source_url=movie_url,
        source_url_field="colombia_dot_com_url",
        metadata=metadata,
        tmdb_service=tmdb_service,
        storage_service=storage_service,
        source_name=SOURCE_NAME,
    )

    # Step 4: Use colombia.com classification as fallback if TMDB has no Colombia certification
    if result.movie and result.is_new and metadata and metadata.classification:
        if not result.movie.age_rating_colombia:
            result.movie.age_rating_colombia = metadata.classification
            result.movie.save(update_fields=["age_rating_colombia"])
            logger.info(f"Using colombia.com classification '{metadata.classification}' for {result.movie}")

    return result


# TODO: When we have more than one worker, this transaction will cause problems.
# If another worker adds a movie while this adds the same movie, the transaction will fail.
@transaction.atomic
def save_showtimes_for_theater(theater: Theater) -> TaskReport:
    """
    Scrape showtimes from a theater for all available dates and save to the database.

    Returns:
        TaskReport with stats for this theater
    """
    html_content = asyncio.run(_scrape_theater_html_async(theater, target_date=None))
    date_options = _find_date_options(html_content)

    if not date_options:
        logger.warning(f"No date options found for theater: {theater.name}")
        OperationalIssue.objects.create(
            name="No Date Options Found",
            task="save_showtimes_for_theater",
            error_message=f"No date options found in dropdown for theater: {theater.name}",
            context={"theater_id": theater.id, "theater_name": theater.name, "url": theater.colombia_dot_com_url},  # pyright: ignore[reportAttributeAccessIssue]
            severity=OperationalIssue.Severity.WARNING,
        )
        return TaskReport(total_showtimes=0, tmdb_calls=0, new_movies=[])

    logger.info(f"Found {len(date_options)} dates for {theater.name}: {date_options}\n\n")

    tmdb_service = TMDBService()
    storage_service = create_storage_service()
    total_showtimes = 0
    total_tmdb_calls = 0
    all_new_movies: list[str] = []
    today = datetime.datetime.now(BOGOTA_TZ).date()

    for target_date in date_options:
        if target_date == today:
            report = _save_showtimes_for_theater_for_date(
                theater=theater,
                target_date=None,
                tmdb_service=tmdb_service,
                storage_service=storage_service,
                html_content=html_content,
            )
        else:
            report = _save_showtimes_for_theater_for_date(
                theater=theater,
                target_date=target_date,
                tmdb_service=tmdb_service,
                storage_service=storage_service,
                html_content=None,
            )
        total_showtimes += report.total_showtimes
        total_tmdb_calls += report.tmdb_calls
        for movie_title in report.new_movies:
            if movie_title not in all_new_movies:
                all_new_movies.append(movie_title)

    logger.info(f"Processing finished. Saved {total_showtimes} total showtimes for {theater.name}\n\n\n")
    return TaskReport(
        total_showtimes=total_showtimes,
        tmdb_calls=total_tmdb_calls,
        new_movies=all_new_movies,
    )


def _save_showtimes_for_theater_for_date(
    theater: Theater,
    target_date: datetime.date | None,
    tmdb_service: TMDBService,
    storage_service,
    html_content: str | None,
) -> TaskReport:
    """
    Scrape showtimes for a specific date and save them to the database.

    If target_date is None, scrapes the default page (today's showtimes).
    If html_content is provided, uses it instead of scraping.

    Returns:
        TaskReport with stats for this date
    """
    if not html_content:
        html_content = asyncio.run(_scrape_theater_html_async(theater, target_date=target_date))
    movie_showtimes_list = _extract_showtimes_from_html(html_content)

    effective_date = target_date or datetime.datetime.now(BOGOTA_TZ).date()

    if not movie_showtimes_list:
        logger.warning(f"No showtimes found for theater: {theater.name} on {effective_date}")
        return TaskReport(total_showtimes=0, tmdb_calls=0, new_movies=[])

    logger.info(f"Processing showtimes for {theater.name} on {effective_date}")

    source_url = theater.colombia_dot_com_url
    deleted_count, _ = Showtime.objects.filter(theater=theater, start_date=effective_date).delete()
    if deleted_count:
        logger.info(f"Deleted {deleted_count} existing showtimes for {theater.name} on {effective_date}")

    showtimes_saved = 0
    tmdb_calls = 0
    new_movies: list[str] = []

    for movie_showtime in movie_showtimes_list:
        lookup_result = _get_or_create_movie_colombia(
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
            continue

        for description in movie_showtime.descriptions:
            for start_time in description.start_times:
                Showtime.objects.create(
                    theater=theater,
                    movie=lookup_result.movie,
                    start_date=effective_date,
                    start_time=start_time,
                    format=description.description,
                    source_url=source_url,
                )
                showtimes_saved += 1

    logger.info(f"Saved {showtimes_saved} showtimes for {theater.name} on {effective_date}\n\n")
    return TaskReport(
        total_showtimes=showtimes_saved,
        tmdb_calls=tmdb_calls,
        new_movies=new_movies,
    )


@app.task
def colombia_com_download_task():
    """
    Celery task to download movie showtime data from colombia.com.

    Iterates through all theaters with a colombia_dot_com_url,
    scrapes showtimes, fetches TMDB data, and saves to the database.

    Scheduled to run every 10 minutes.
    """
    logger.info("Starting colombia_com_download_task")

    theaters = Theater.objects.exclude(colombia_dot_com_url__isnull=True).exclude(
        colombia_dot_com_url=""
    )

    theater_count = theaters.count()
    if theater_count == 0:
        logger.warning("No theaters found with colombia_dot_com_url")
        return

    logger.info(f"Found {theater_count} theaters with colombia_dot_com_url\n\n")

    total_showtimes = 0
    total_tmdb_calls = 0
    all_new_movies: list[str] = []
    failed_theaters: list[str] = []

    for theater in theaters:
        try:
            logger.info(f"Starting to process theater: {theater.name}")
            report = save_showtimes_for_theater(theater)
            total_showtimes += report.total_showtimes
            total_tmdb_calls += report.tmdb_calls
            for movie_title in report.new_movies:
                if movie_title not in all_new_movies:
                    all_new_movies.append(movie_title)
        except Exception as e:
            logger.error(f"Failed to process theater '{theater.name}': {e}")
            OperationalIssue.objects.create(
                name="Theater Processing Failed",
                task="colombia_com_download_task",
                error_message=str(e),
                traceback=traceback.format_exc(),
                context={"theater_id": theater.id, "theater_name": theater.name, "url": theater.colombia_dot_com_url},  # pyright: ignore[reportAttributeAccessIssue]
                severity=OperationalIssue.Severity.ERROR,
            )
            failed_theaters.append(theater.name)
            continue

    final_report = TaskReport(
        total_showtimes=total_showtimes,
        tmdb_calls=total_tmdb_calls,
        new_movies=all_new_movies,
    )
    final_report.print_report()

    if failed_theaters:
        logger.warning(f"Failed theaters: {failed_theaters}")
