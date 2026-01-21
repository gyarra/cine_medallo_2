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
import unicodedata
import zoneinfo
from dataclasses import dataclass

from bs4 import BeautifulSoup
from django.db import transaction
from camoufox.async_api import AsyncCamoufox

from config.celery_app import app
from movies_app.models import APICallCounter, Movie, OperationalIssue, Showtime, Theater
from movies_app.services.tmdb_service import TMDBMovieResult, TMDBService, TMDBServiceError

logger = logging.getLogger(__name__)

# Browser configuration
BROWSER_TIMEOUT_SECONDS = 120

# Colombia timezone
BOGOTA_TZ = zoneinfo.ZoneInfo("America/Bogota")

# Base URL for colombia.com
COLOMBIA_COM_BASE_URL = "https://www.colombia.com"


@dataclass
class ShowtimeDescription:
    description: str
    start_times: list[datetime.time]


@dataclass
class MovieMetadata:
    genre: str
    duration_minutes: int | None
    classification: str
    director: str
    actors: list[str]
    release_date: str


@dataclass
class MovieShowtimes:
    movie_name: str
    movie_url: str | None
    descriptions: list[ShowtimeDescription]


@dataclass
class MovieLookupResult:
    movie: Movie | None
    is_new: bool
    tmdb_called: bool


@dataclass
class TaskReport:
    total_showtimes: int
    tmdb_calls: int
    new_movies: list[str]

    def print_report(self) -> None:
        logger.info("\n\n")
        logger.info("=" * 50)
        logger.info("TASK REPORT")
        logger.info("=" * 50)
        logger.info(f"Total showtimes added: {self.total_showtimes}")
        logger.info(f"TMDB API calls made: {self.tmdb_calls}")
        logger.info(f"New movies added: {len(self.new_movies)}")
        if self.new_movies:
            for movie_title in self.new_movies:
                logger.info(f"  - {movie_title}")
        logger.info("=" * 50)


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
    return dates


def _extract_movie_metadata_from_html(html_content: str) -> MovieMetadata | None:
    """
    Extract movie metadata from colombia.com individual movie page HTML.

    Parses: Género, Duración, Clasificación, Director, Actores, Fecha de estreno
    """
    soup = BeautifulSoup(html_content, "lxml")

    genre = ""
    duration_minutes: int | None = None
    classification = ""
    director = ""
    actors: list[str] = []
    release_date = ""

    # Find the movie info section (within class "pelicula")
    movie_div = soup.find("div", class_="pelicula")
    if not movie_div:
        return None

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

    return MovieMetadata(
        genre=genre,
        duration_minutes=duration_minutes,
        classification=classification,
        director=director,
        actors=actors,
        release_date=release_date,
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
                await page.select_option("select[name='fecha']", date_value)
                await page.wait_for_load_state("domcontentloaded")

            html_content = await page.content()
        finally:
            await context.close()
    logger.info(f"Finished scraping showtimes for theater: {theater.name}\n")

    return html_content


def _normalize_name(name: str) -> str:
    """Normalize a name for comparison by lowercasing and removing accents/punctuation."""
    normalized = unicodedata.normalize("NFD", name.lower())
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").strip()


def _find_best_tmdb_match(
    results: list[TMDBMovieResult],
    movie_name: str,
    metadata: MovieMetadata | None,
    tmdb_service: TMDBService,
) -> TMDBMovieResult | None:
    """
    Find the best matching TMDB result using colombia.com metadata for verification.

    Matching priority:
    1. Exact release date match
    2. Release year match (within 1 year tolerance)
    3. Director/actors match (fetches details from TMDB)
    4. Title similarity

    Returns the best match, or None if no suitable match is found.
    """
    logger.debug(f"=== _find_best_tmdb_match START for '{movie_name}' ===")
    logger.debug(f"  TMDB results count: {len(results)}")
    logger.debug(f"  Has metadata: {metadata is not None}")

    if not results:
        logger.debug("  No TMDB results, returning None")
        return None

    # If no metadata, fall back to first result
    if not metadata:
        logger.info(f"No metadata available for '{movie_name}', using first TMDB result")
        logger.debug(f"  Falling back to first result: '{results[0].title}' (id={results[0].id})")
        OperationalIssue.objects.create(
            name="No Colombia.com Metadata",
            task="_find_best_tmdb_match",
            error_message=f"Could not extract metadata from colombia.com for '{movie_name}'",
            context={"movie_name": movie_name},
            severity=OperationalIssue.Severity.WARNING,
        )
        return results[0]

    logger.debug(f"  Metadata: director='{metadata.director}', actors={metadata.actors}")
    logger.debug(f"  Metadata: release_date='{metadata.release_date}', duration={metadata.duration_minutes}")

    colombia_date = _parse_release_date_from_colombia_date(metadata.release_date)
    colombia_year = _parse_release_year_from_colombia_date(metadata.release_date)
    logger.debug(f"  Parsed colombia_date={colombia_date}, colombia_year={colombia_year}")

    if not colombia_year:
        logger.warning(f"Could not parse release date from '{metadata.release_date}' for '{movie_name}'")
        OperationalIssue.objects.create(
            name="Missing Colombia.com Release Date",
            task="_find_best_tmdb_match",
            error_message=f"Could not parse release date from colombia.com for '{movie_name}'",
            context={
                "movie_name": movie_name,
                "release_date_raw": metadata.release_date,
                "metadata": {
                    "genre": metadata.genre,
                    "duration_minutes": metadata.duration_minutes,
                    "director": metadata.director,
                },
            },
            severity=OperationalIssue.Severity.WARNING,
        )

    best_match: TMDBMovieResult | None = None
    best_score = -1
    has_date_match = False

    logger.debug(f"  --- Starting loop over {len(results)} TMDB results ---")

    for idx, result in enumerate(results):
        logger.debug(f"  [{idx}] Evaluating: '{result.title}' (id={result.id}, release={result.release_date})")
        score = 0

        # Parse TMDB date
        tmdb_date: datetime.date | None = None
        tmdb_year: int | None = None
        if result.release_date:
            try:
                tmdb_date = datetime.datetime.strptime(result.release_date, "%Y-%m-%d").date()
                tmdb_year = tmdb_date.year
            except ValueError:
                logger.debug(f"      Failed to parse TMDB date: '{result.release_date}'")

        logger.debug(f"      tmdb_date={tmdb_date}, tmdb_year={tmdb_year}")

        # Priority 1: Exact date match (strongest signal) - return immediately
        if colombia_date and tmdb_date and colombia_date == tmdb_date:
            logger.info(
                f"Exact date match for '{movie_name}': '{result.title}' "
                f"(id={result.id}, date={tmdb_date})"
            )
            logger.debug("  === EARLY RETURN: Exact date match ===")
            return result

        # Priority 2: Year match
        elif colombia_year and tmdb_year:
            year_diff = abs(colombia_year - tmdb_year)
            logger.debug(f"      Year comparison: colombia={colombia_year}, tmdb={tmdb_year}, diff={year_diff}")
            if year_diff == 0:
                score += 100
                has_date_match = True
                logger.debug("      +100 (same year)")
            elif year_diff == 1:
                # Allow 1 year difference for release timing differences between countries
                score += 50
                has_date_match = True
                logger.debug("      +50 (year diff = 1)")
            else:
                # Significant year mismatch is a strong negative signal
                score -= 50
                logger.debug("      -50 (year diff > 1)")

        # Title similarity bonus
        movie_name_lower = movie_name.lower()
        tmdb_title_lower = result.title.lower()
        original_title_lower = result.original_title.lower()

        if movie_name_lower == tmdb_title_lower:
            score += 30
            logger.debug("      +30 (exact title match)")
        elif movie_name_lower in tmdb_title_lower or tmdb_title_lower in movie_name_lower:
            score += 15
            logger.debug("      +15 (partial title match)")

        if movie_name_lower == original_title_lower:
            score += 20
            logger.debug("      +20 (exact original_title match)")
        elif movie_name_lower in original_title_lower or original_title_lower in movie_name_lower:
            score += 10
            logger.debug("      +10 (partial original_title match)")

        # Popularity boost (TMDB orders by relevance, so add small position-based bonus)
        position_bonus = max(0, 10 - idx)
        score += position_bonus
        logger.debug(f"      +{position_bonus} (position bonus)")

        # Director/actors matching - only fetch details if we have metadata to compare
        # and limit to top 5 results to avoid excessive API calls
        director_matched = False
        actor_matched = False
        if metadata and (metadata.director or metadata.actors) and idx < 5:
            logger.debug("      Fetching TMDB details for credits comparison...")
            try:
                APICallCounter.increment("tmdb")
                details = tmdb_service.get_movie_details(result.id, include_credits=True)
                logger.debug(f"      Got details: {len(details.directors)} directors, {len(details.cast) if details.cast else 0} cast")

                # Director matching
                if metadata.director and details.directors:
                    colombia_director = _normalize_name(metadata.director)
                    tmdb_director_names = [d.name for d in details.directors]
                    logger.debug(f"      Director comparison: colombia='{colombia_director}', tmdb={tmdb_director_names}")
                    for tmdb_director in details.directors:
                        if _normalize_name(tmdb_director.name) == colombia_director:
                            score += 150
                            director_matched = True
                            logger.debug(f"      +150 (director match: {tmdb_director.name})")
                            break

                # Actors matching - check if any colombia.com actor appears in TMDB cast
                if metadata.actors and details.cast:
                    colombia_actors = {_normalize_name(a) for a in metadata.actors}
                    tmdb_actors = {_normalize_name(c.name) for c in details.cast[:15]}  # Top 15 cast
                    matching_actors = colombia_actors & tmdb_actors
                    logger.debug(f"      Actor comparison: colombia={colombia_actors}")
                    logger.debug(f"      Actor comparison: tmdb={tmdb_actors}")
                    logger.debug(f"      Matching actors: {matching_actors}")
                    if matching_actors:
                        # Score based on number of matching actors
                        actor_score = min(len(matching_actors) * 30, 90)  # Cap at 90
                        score += actor_score
                        actor_matched = True
                        logger.debug(f"      +{actor_score} (actor match: {len(matching_actors)} actors)")
            except TMDBServiceError as e:
                logger.warning(f"Failed to fetch details for TMDB id {result.id}: {e}")

        logger.debug(
            f"      FINAL SCORE: {score} (director_matched={director_matched}, actor_matched={actor_matched})"
        )

        if score > best_score:
            logger.debug(f"      New best match! (previous best_score={best_score})")
            best_score = score
            best_match = result

    logger.debug("  --- Loop complete ---")

    # Log operational issue if we couldn't match by date
    if not has_date_match and (colombia_date or colombia_year):
        tmdb_dates = [
            f"{r.title}: {r.release_date}" for r in results[:5]  # First 5 results
        ]
        logger.debug("  No date match found, creating OperationalIssue")
        OperationalIssue.objects.create(
            name="No TMDB Date Match",
            task="_find_best_tmdb_match",
            error_message=f"No TMDB result matched release date for '{movie_name}'",
            context={
                "movie_name": movie_name,
                "colombia_date": str(colombia_date) if colombia_date else None,
                "colombia_year": colombia_year,
                "tmdb_results": tmdb_dates,
            },
            severity=OperationalIssue.Severity.WARNING,
        )

    if best_match:
        logger.info(
            f"Selected TMDB match for '{movie_name}': '{best_match.title}' "
            f"(id={best_match.id}, score={best_score}, date_matched={has_date_match})"
        )
        logger.debug(f"=== _find_best_tmdb_match END: returning '{best_match.title}' ===")
    else:
        logger.warning(f"No suitable TMDB match found for '{movie_name}'")
        logger.debug("=== _find_best_tmdb_match END: returning None ===")

    return best_match


def _get_or_create_movie(
    movie_name: str,
    movie_url: str | None,
    tmdb_service: TMDBService,
) -> MovieLookupResult:
    """
    Get or create a movie, prioritizing lookup by colombia.com URL.

    Lookup order:
    1. By colombia_dot_com_url (if provided) - avoids TMDB API call
    2. By TMDB search - only if URL lookup fails

    For new movies, scrapes the colombia.com movie page to gather additional
    metadata for better TMDB match verification.
    """
    # First, try to find existing movie by colombia.com URL
    if movie_url:
        existing_movie = Movie.objects.filter(colombia_dot_com_url=movie_url).first()
        if existing_movie:
            return MovieLookupResult(movie=existing_movie, is_new=False, tmdb_called=False)

    # No URL match - need to search TMDB
    try:
        logger.info(f"Did not find movie: '{movie_name}'. Searching TMDB...")
        APICallCounter.increment("tmdb")
        response = tmdb_service.search_movie(movie_name)

        if not response.results:
            logger.warning(f"No TMDB results found for: {movie_name}")
            return MovieLookupResult(movie=None, is_new=False, tmdb_called=True)

        # For existing movies, check if first result already exists in DB
        first_result = response.results[0]
        existing_movie = Movie.objects.filter(tmdb_id=first_result.id).first()
        if existing_movie:
            # Update URL if we have it and the movie doesn't
            if movie_url and not existing_movie.colombia_dot_com_url:
                existing_movie.colombia_dot_com_url = movie_url
                existing_movie.save(update_fields=["colombia_dot_com_url"])
            return MovieLookupResult(movie=existing_movie, is_new=False, tmdb_called=True)

        # New movie - scrape metadata from colombia.com for better matching
        metadata: MovieMetadata | None = None
        if movie_url:
            try:
                movie_html = asyncio.run(_scrape_movie_page_async(movie_url))
                metadata = _extract_movie_metadata_from_html(movie_html)
                if metadata:
                    logger.info(
                        f"Scraped metadata for '{movie_name}': "
                        f"genre={metadata.genre}, duration={metadata.duration_minutes}, "
                        f"release_date={metadata.release_date}, director={metadata.director}"
                    )
            except Exception as e:
                logger.warning(f"Failed to scrape movie page for '{movie_name}': {e}")

        # Find best matching TMDB result
        best_match = _find_best_tmdb_match(response.results, movie_name, metadata, tmdb_service)
        if not best_match:
            return MovieLookupResult(movie=None, is_new=False, tmdb_called=True)

        # Check if this match already exists
        existing_movie = Movie.objects.filter(tmdb_id=best_match.id).first()
        if existing_movie:
            # Update URL if we have it and the movie doesn't
            if movie_url and not existing_movie.colombia_dot_com_url:
                existing_movie.colombia_dot_com_url = movie_url
                existing_movie.save(update_fields=["colombia_dot_com_url"])
            return MovieLookupResult(movie=existing_movie, is_new=False, tmdb_called=True)

        movie = Movie.create_from_tmdb(best_match)
        if movie_url:
            movie.colombia_dot_com_url = movie_url
            movie.save(update_fields=["colombia_dot_com_url"])
        logger.info(f"Created movie: {movie}")

        return MovieLookupResult(movie=movie, is_new=True, tmdb_called=True)

    except TMDBServiceError as e:
        logger.error(f"TMDB error for '{movie_name}': {e}")
        OperationalIssue.objects.create(
            name="TMDB API Error",
            task="_get_or_create_movie",
            error_message=str(e),
            traceback=traceback.format_exc(),
            context={"movie_name": movie_name, "movie_url": movie_url},
            severity=OperationalIssue.Severity.ERROR,
        )
        return MovieLookupResult(movie=None, is_new=False, tmdb_called=True)


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
                html_content=html_content,
            )
        else:
            report = _save_showtimes_for_theater_for_date(
                theater=theater,
                target_date=target_date,
                tmdb_service=tmdb_service,
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
        lookup_result = _get_or_create_movie(
            movie_name=movie_showtime.movie_name,
            movie_url=movie_showtime.movie_url,
            tmdb_service=tmdb_service,
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

    logger.info(f"Saved {showtimes_saved} showtimes for {theater.name} on {effective_date}")
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

    logger.info(f"Found {theater_count} theaters with colombia_dot_com_url")

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
