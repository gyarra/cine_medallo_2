"""
Download From Colombia.com Task

Celery task for scraping movie showtime data from colombia.com.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup
from camoufox.async_api import AsyncCamoufox

from config.celery_app import app
from movies_app.models import Movie, Theater
from movies_app.services.tmdb_service import TMDBService, TMDBServiceError

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Browser configuration
BROWSER_TIMEOUT_SECONDS = 120


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


async def _scrape_theater_movies_async(theater: Theater) -> list[str]:
    """
    Async implementation of theater movie scraping using Camoufox.

    Returns:
        List of movie names found on the theater page.
    """
    if not theater.colombia_dot_com_url:
        raise ValueError(f"Theater '{theater.name}' has no colombia_dot_com_url")

    logger.info(f"Scraping movies for theater: {theater.name}")
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

    movie_names = _extract_movie_names_from_html(html_content)
    logger.info(f"Found {len(movie_names)} movies for {theater.name}: {movie_names}")

    return movie_names


def scrape_theater_movies(theater: Theater) -> list[str]:
    """
    Used only by the command to run the scraper synchronously.
    """
    return asyncio.run(_scrape_theater_movies_async(theater))


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
        try:
            response = tmdb_service.search_movie(movie_name)

            if not response.results:
                logger.warning(f"No TMDB results found for: {movie_name}")
                continue

            # Pick the first result
            tmdb_result = response.results[0]

            movie, created = Movie.get_or_create_from_tmdb(tmdb_result)
            if created:
                logger.info(f"Created movie: {movie}")
            else:
                logger.info(f"Movie already exists: {movie}")

            saved_movies.append(movie_name)

        except TMDBServiceError as e:
            logger.error(f"TMDB error for '{movie_name}': {e}")
            continue

    logger.info(f"Saved {len(saved_movies)}/{len(movie_names)} movies for {theater.name}")
    return saved_movies


@app.task
def colombia_com_download_task():
    """
    Celery task to download movie showtime data from colombia.com.

    Iterates through all theaters with a colombia_dot_com_url,
    scrapes movie names, fetches TMDB data, and saves to the database.

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

    total_saved = 0
    failed_theaters: list[str] = []

    for theater in theaters:
        try:
            logger.info(f"Processing theater: {theater.name}")
            saved_movies = save_movies_for_theater(theater)
            total_saved += len(saved_movies)
        except Exception as e:
            logger.error(f"Failed to process theater '{theater.name}': {e}")
            failed_theaters.append(theater.name)
            continue

    logger.info(
        f"colombia_com_download_task completed: "
        f"{total_saved} movies saved, {len(failed_theaters)} theaters failed"
    )

    if failed_theaters:
        logger.warning(f"Failed theaters: {failed_theaters}")
