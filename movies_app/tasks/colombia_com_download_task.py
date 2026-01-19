"""
Download From Colombia.com Task

Celery task for scraping movie showtime data from colombia.com.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
import zoneinfo
from dataclasses import dataclass
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from camoufox.async_api import AsyncCamoufox

from config.celery_app import app
from movies_app.models import Movie, Showtime, Theater
from movies_app.services.tmdb_service import TMDBService, TMDBServiceError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Browser configuration
BROWSER_TIMEOUT_SECONDS = 120

# Colombia timezone
BOGOTA_TZ = zoneinfo.ZoneInfo("America/Bogota")


@dataclass
class ShowtimeDescription:
    description: str
    start_times: list[datetime.time]


@dataclass
class MovieShowtimes:
    movie_name: str
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

    Returns a list of MovieShowtimes, each containing the movie name
    and a list of ShowtimeDescription objects (format/language + times).
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
            result.append(MovieShowtimes(movie_name=movie_name, descriptions=descriptions))

    return result


def _extract_movie_names_from_html(html_content: str) -> list[str]:
    """
    Extract movie names from colombia.com theater page HTML.

    Returns:
        List of movie names found in the HTML.
    """
    soup = BeautifulSoup(html_content, "lxml")
    movie_divs = soup.find_all("div", class_="nombre-pelicula")

    movie_names = []
    for div in movie_divs:
        anchor = div.find("a")
        if anchor and anchor.string:
            movie_names.append(anchor.string.strip())

    return movie_names


async def _scrape_theater_html_async(theater: Theater) -> str:
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
            html_content = await page.content()
        finally:
            await context.close()

    return html_content


async def _scrape_theater_movies_async(theater: Theater) -> list[str]:
    """
    Async implementation of theater movie scraping using Camoufox.

    Returns:
        List of movie names found on the theater page.
    """
    html_content = await _scrape_theater_html_async(theater)
    movie_names = _extract_movie_names_from_html(html_content)
    logger.info(f"Found {len(movie_names)} movies for {theater.name}: {movie_names}")

    return movie_names


def scrape_theater_movies(theater: Theater) -> list[str]:
    """Used only by the command to run the scraper synchronously."""
    return asyncio.run(_scrape_theater_movies_async(theater))


def _get_or_create_movie(movie_name: str, tmdb_service: TMDBService) -> Movie | None:
    """Look up movie in TMDB and get or create it in the database."""
    try:
        response = tmdb_service.search_movie(movie_name)

        if not response.results:
            logger.warning(f"No TMDB results found for: {movie_name}")
            return None

        tmdb_result = response.results[0]
        movie, created = Movie.get_or_create_from_tmdb(tmdb_result)

        if created:
            logger.info(f"Created movie: {movie}")

        return movie

    except TMDBServiceError as e:
        logger.error(f"TMDB error for '{movie_name}': {e}")
        return None


def save_showtimes_for_theater(theater: Theater) -> int:
    """
    Scrape showtimes from a theater and save them to the database.

    1. Scrape HTML from colombia.com
    2. Extract showtimes from HTML
    3. For each movie, get or create it via TMDB
    4. Delete existing showtimes for this theater on today's date
    5. Save new showtimes

    Returns:
        Number of showtimes saved
    """
    html_content = asyncio.run(_scrape_theater_html_async(theater))
    movie_showtimes_list = _extract_showtimes_from_html(html_content)

    if not movie_showtimes_list:
        logger.warning(f"No showtimes found for theater: {theater.name}")
        return 0

    today = datetime.datetime.now(BOGOTA_TZ).date()
    source_url = theater.colombia_dot_com_url or ""
    tmdb_service = TMDBService()

    # Delete existing showtimes for this theater on today's date
    deleted_count, _ = Showtime.objects.filter(theater=theater, start_date=today).delete()
    if deleted_count:
        logger.info(f"Deleted {deleted_count} existing showtimes for {theater.name} on {today}")

    showtimes_saved = 0

    for movie_showtime in movie_showtimes_list:
        movie = _get_or_create_movie(movie_showtime.movie_name, tmdb_service)
        if not movie:
            continue

        for description in movie_showtime.descriptions:
            for start_time in description.start_times:
                try:
                    Showtime.objects.create(
                        theater=theater,
                        movie=movie,
                        start_date=today,
                        start_time=start_time,
                        format=description.description,
                        source_url=source_url,
                    )
                    showtimes_saved += 1
                except Exception as e:
                    logger.error(
                        f"Failed to save showtime for {movie_showtime.movie_name} "
                        f"at {start_time}: {e}"
                    )

    logger.info(f"Saved {showtimes_saved} showtimes for {theater.name}")
    return showtimes_saved


def save_movies_for_theater(theater: Theater) -> list[str]:
    """
    Scrape movie names from a theater and save them to the database.

    For each movie name scraped from colombia.com:
    1. Search TMDB for the movie
    2. If found, upsert the movie in the database (first result is used)
    3. If not found on TMDB, skip the movie

    Returns:
        List of movie names that were successfully saved
    """
    movie_names = asyncio.run(_scrape_theater_movies_async(theater))
    saved_movies: list[str] = []

    tmdb_service = TMDBService()

    for movie_name in movie_names:
        movie = _get_or_create_movie(movie_name, tmdb_service)
        if movie:
            saved_movies.append(movie_name)

    logger.info(f"Saved {len(saved_movies)}/{len(movie_names)} movies for {theater.name}")
    return saved_movies


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
    failed_theaters: list[str] = []

    for theater in theaters:
        try:
            logger.info(f"Processing theater: {theater.name}")
            showtimes_saved = save_showtimes_for_theater(theater)
            total_showtimes += showtimes_saved
        except Exception as e:
            logger.error(f"Failed to process theater '{theater.name}': {e}")
            failed_theaters.append(theater.name)
            continue

    logger.info(
        f"colombia_com_download_task completed: "
        f"{total_showtimes} showtimes saved, {len(failed_theaters)} theaters failed"
    )

    if failed_theaters:
        logger.warning(f"Failed theaters: {failed_theaters}")
