"""
MAMM (elmamm.org) Scraper Task

Celery task and utilities for scraping movie showtime data from
Museo de Arte Moderno de Medellín (MAMM).

The weekly schedule is at: https://www.elmamm.org/cine/#semana
Individual movie pages are at: https://www.elmamm.org/producto/<slug>/
"""

from __future__ import annotations

import datetime
import logging
import re
import zoneinfo
from dataclasses import dataclass

import requests
from bs4 import BeautifulSoup
from django.db import transaction

from movies_app.models import Movie, MovieSourceUrl, OperationalIssue, Showtime, Theater
from movies_app.services.movie_lookup_result import MovieLookupResult
from movies_app.services.movie_lookup_service import MovieLookupService
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.download_utilities import MovieMetadata, TaskReport

logger = logging.getLogger(__name__)

BOGOTA_TZ = zoneinfo.ZoneInfo("America/Bogota")
MAMM_BASE_URL = "https://www.elmamm.org"
MAMM_CINE_URL = "https://www.elmamm.org/cine/"
SOURCE_NAME = "mamm"
REQUEST_TIMEOUT_SECONDS = 30

SPANISH_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


@dataclass
class MAMMShowtime:
    """A single showtime extracted from the MAMM weekly schedule."""
    movie_title: str
    movie_url: str | None
    date: datetime.date
    time: datetime.time
    special_label: str


@dataclass
class MAMMMovieMetadata:
    """Metadata extracted from a MAMM movie detail page."""
    title: str
    age_rating: str
    duration_minutes: int | None
    director: str
    year: int | None
    country: str
    synopsis: str
    poster_url: str
    trailer_url: str


def _fetch_html(url: str) -> str:
    """Fetch HTML content from a URL."""
    response = requests.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
    response.raise_for_status()
    return response.text


def _parse_time_string(time_str: str) -> datetime.time | None:
    """
    Parse MAMM time format like '2:00 pm' or '9:30 pm' to datetime.time.
    """
    time_str = time_str.strip().lower()
    match = re.match(r"(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)", time_str)
    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))
    period = match.group(3).replace(".", "")

    if period == "pm" and hour != 12:
        hour += 12
    elif period == "am" and hour == 12:
        hour = 0

    return datetime.time(hour, minute)


def _parse_date_string(date_str: str, reference_year: int) -> datetime.date | None:
    """
    Parse MAMM date format like 'viernes 23 Ene' to datetime.date.

    Args:
        date_str: Date string from the schedule (e.g., 'viernes 23 Ene')
        reference_year: The year to use (inferred from current date)
    """
    match = re.search(r"(\d{1,2})\s+(\w{3})", date_str, re.IGNORECASE)
    if not match:
        return None

    day = int(match.group(1))
    month_abbr = match.group(2).lower()
    month = SPANISH_MONTHS.get(month_abbr)

    if not month:
        return None

    try:
        return datetime.date(reference_year, month, day)
    except ValueError:
        return None


def _extract_showtimes_from_html(html_content: str) -> list[MAMMShowtime]:
    """
    Extract movie showtimes from the MAMM weekly schedule HTML.

    Parses the #semana section containing the weekly schedule grid.
    """
    soup = BeautifulSoup(html_content, "lxml")

    schedule_section = soup.find("section", class_="schedule-week")
    if not schedule_section:
        logger.warning("Could not find schedule-week section in MAMM HTML")
        return []

    showtimes: list[MAMMShowtime] = []
    today = datetime.datetime.now(BOGOTA_TZ).date()
    reference_year = today.year

    columns = schedule_section.find_all("div", class_="col")

    for col in columns:
        day_div = col.find("div", class_="day")
        if not day_div:
            continue

        day_text_elem = day_div.find("p", class_="small")
        if not day_text_elem:
            continue

        day_text = day_text_elem.get_text(strip=True)
        parsed_date = _parse_date_string(day_text, reference_year)

        if not parsed_date:
            logger.warning(f"Could not parse date: {day_text}")
            continue

        if parsed_date < today and parsed_date.month < today.month:
            parsed_date = datetime.date(reference_year + 1, parsed_date.month, parsed_date.day)

        cards = col.find_all("div", class_="card")

        for card in cards:
            anchor = card.find("a")
            if not anchor:
                continue

            time_elem = anchor.find("p", class_="small")
            title_elem = anchor.find("h3")

            if not time_elem or not title_elem:
                continue

            time_text = time_elem.get_text(strip=True)
            movie_title = title_elem.get_text(strip=True)

            parsed_time = _parse_time_string(time_text)
            if not parsed_time:
                logger.warning(f"Could not parse time: {time_text}")
                continue

            movie_url: str | None = None
            href = anchor.get("href")
            if href and isinstance(href, str) and href.startswith("http"):
                movie_url = href

            special_label = ""
            ciclo_span = card.find("span", class_="ciclo")
            if ciclo_span:
                special_label = ciclo_span.get_text(strip=True)

            showtimes.append(MAMMShowtime(
                movie_title=movie_title,
                movie_url=movie_url,
                date=parsed_date,
                time=parsed_time,
                special_label=special_label,
            ))

    return showtimes


def _extract_movie_metadata_from_html(html_content: str) -> MAMMMovieMetadata | None:
    """
    Extract movie metadata from a MAMM movie detail page.
    """
    soup = BeautifulSoup(html_content, "lxml")

    title_elem = soup.find("h1", class_="product_title")
    if not title_elem:
        return None

    title = title_elem.get_text(strip=True)

    age_rating = ""
    duration_minutes: int | None = None
    director = ""
    year: int | None = None
    country = ""
    synopsis = ""
    poster_url = ""
    trailer_url = ""

    short_desc = soup.find("div", class_="woocommerce-product-details__short-description")
    if short_desc:
        paragraphs = short_desc.find_all("p")
        for p in paragraphs:
            text = p.get_text(strip=True)

            if "|" in text and "min" in text.lower():
                parts = text.split("|")
                if len(parts) >= 1:
                    age_rating = parts[0].strip()
                if len(parts) >= 2:
                    duration_match = re.search(r"(\d+)\s*min", parts[1], re.IGNORECASE)
                    if duration_match:
                        duration_minutes = int(duration_match.group(1))

            elif text.lower().startswith("director:"):
                director = text.replace("Director:", "").replace("director:", "").strip()

            elif re.match(r"^\d{4}\s*\|", text):
                parts = text.split("|")
                if len(parts) >= 1:
                    year_match = re.match(r"(\d{4})", parts[0].strip())
                    if year_match:
                        year = int(year_match.group(1))
                if len(parts) >= 2:
                    country = parts[1].strip()

            elif not synopsis and len(text) > 50:
                synopsis = text

    gallery_img = soup.find("div", class_="woocommerce-product-gallery__image")
    if gallery_img:
        img = gallery_img.find("img")
        if img and img.get("src"):
            poster_url = str(img["src"])

    description_tab = soup.find("div", id="tab-description")
    if description_tab:
        iframe = description_tab.find("iframe")
        if iframe and iframe.get("src"):
            src = str(iframe["src"])
            if "youtube" in src:
                video_match = re.search(r"embed/([a-zA-Z0-9_-]+)", src)
                if video_match:
                    trailer_url = f"https://www.youtube.com/watch?v={video_match.group(1)}"

    return MAMMMovieMetadata(
        title=title,
        age_rating=age_rating,
        duration_minutes=duration_minutes,
        director=director,
        year=year,
        country=country,
        synopsis=synopsis,
        poster_url=poster_url,
        trailer_url=trailer_url,
    )


def _scrape_movie_metadata(movie_url: str, movie_title: str) -> MovieMetadata | None:
    """
    Scrape metadata from a MAMM movie detail page.

    Returns MovieMetadata or None if scraping fails.
    """
    try:
        html_content = _fetch_html(movie_url)
        mamm_meta = _extract_movie_metadata_from_html(html_content)

        if not mamm_meta:
            logger.warning(f"Could not extract metadata from MAMM page for '{movie_title}'")
            return None

        return MovieMetadata(
            genre="",
            duration_minutes=mamm_meta.duration_minutes,
            classification=mamm_meta.age_rating,
            director=mamm_meta.director,
            actors=[],
            original_title=None,
            release_date=None,
            release_year=mamm_meta.year,
        )

    except Exception as e:
        logger.warning(f"Failed to scrape MAMM movie page for '{movie_title}': {e}")
        OperationalIssue.objects.create(
            name="MAMM Movie Page Scrape Failed",
            task="_scrape_movie_metadata",
            error_message=f"Failed to scrape MAMM movie page for '{movie_title}': {e}",
            context={"movie_title": movie_title, "movie_url": movie_url},
            severity=OperationalIssue.Severity.WARNING,
        )
        return None


def _get_or_create_movie_mamm(
    movie_title: str,
    movie_url: str | None,
    lookup_service: MovieLookupService,
) -> MovieLookupResult:
    """
    Get or create a movie from MAMM listing.
    """
    if movie_url:
        existing_source_url = MovieSourceUrl.objects.filter(
            scraper_type=MovieSourceUrl.ScraperType.MAMM,
            url=movie_url,
        ).select_related("movie").first()
        if existing_source_url:
            return MovieLookupResult(movie=existing_source_url.movie, is_new=False, tmdb_called=False)

    metadata: MovieMetadata | None = None
    if movie_url:
        metadata = _scrape_movie_metadata(movie_url, movie_title)

    result = lookup_service.get_or_create_movie(
        movie_name=movie_title,
        source_url=movie_url,
        scraper_type=MovieSourceUrl.ScraperType.MAMM,
        metadata=metadata,
    )

    return result


def _get_mamm_theater() -> Theater:
    """
    Get the MAMM theater record.

    Raises:
        Theater.DoesNotExist: If the MAMM theater is not found in the database.
    """
    return Theater.objects.get(slug="museo-de-arte-moderno-de-medellin")


@transaction.atomic
def save_showtimes_from_html(html_content: str) -> TaskReport:
    """
    Parse MAMM schedule HTML and save showtimes to the database.

    Args:
        html_content: HTML content from the MAMM cine page

    Returns:
        TaskReport with stats
    """
    theater = _get_mamm_theater()

    showtimes = _extract_showtimes_from_html(html_content)
    logger.info(f"Extracted {len(showtimes)} showtimes from MAMM schedule")

    tmdb_service = TMDBService()
    storage_service = MovieLookupService.create_storage_service()
    lookup_service = MovieLookupService(tmdb_service, storage_service, SOURCE_NAME)

    total_showtimes = 0
    total_tmdb_calls = 0
    new_movies: list[str] = []
    processed_movies: dict[str, Movie | None] = {}

    for showtime in showtimes:
        cache_key = showtime.movie_url or showtime.movie_title

        if cache_key not in processed_movies:
            result = _get_or_create_movie_mamm(
                movie_title=showtime.movie_title,
                movie_url=showtime.movie_url,
                lookup_service=lookup_service,
            )
            processed_movies[cache_key] = result.movie

            if result.tmdb_called:
                total_tmdb_calls += 1
            if result.is_new and result.movie:
                new_movies.append(result.movie.title_es)

        movie = processed_movies[cache_key]
        if not movie:
            logger.debug(f"Skipping showtime for unfindable movie: {showtime.movie_title}")
            continue

        _, created = Showtime.objects.get_or_create(
            theater=theater,
            movie=movie,
            start_date=showtime.date,
            start_time=showtime.time,
            defaults={
                "format": showtime.special_label,
                "language": "",
                "screen": "",
                "source_url": showtime.movie_url or MAMM_CINE_URL,
            },
        )

        if created:
            total_showtimes += 1
            logger.debug(f"Created showtime: {movie.title_es} at {showtime.date} {showtime.time}")

    logger.info(f"Saved {total_showtimes} new showtimes for MAMM")

    return TaskReport(
        total_showtimes=total_showtimes,
        tmdb_calls=total_tmdb_calls,
        new_movies=new_movies,
    )


def scrape_and_save_mamm_showtimes() -> TaskReport:
    """
    Main entry point: scrape MAMM website and save showtimes.
    """
    logger.info("Starting MAMM scraper...")

    try:
        html_content = _fetch_html(MAMM_CINE_URL)
    except Exception as e:
        logger.error(f"Failed to fetch MAMM cine page: {e}")
        OperationalIssue.objects.create(
            name="MAMM Page Fetch Failed",
            task="scrape_and_save_mamm_showtimes",
            error_message=f"Failed to fetch MAMM cine page: {e}",
            context={"url": MAMM_CINE_URL},
            severity=OperationalIssue.Severity.ERROR,
        )
        raise

    report = save_showtimes_from_html(html_content)
    report.print_report()

    return report
