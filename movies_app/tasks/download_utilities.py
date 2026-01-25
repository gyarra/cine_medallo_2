from __future__ import annotations

import asyncio
import datetime
import logging
import re
import zoneinfo
from dataclasses import dataclass

from camoufox.async_api import AsyncCamoufox

"""
Common utilities for movie download tasks.

This module contains shared functionality used by multiple scrapers
(colombia.com, cine colombia, procinal, etc.) for:
- TMDB movie matching and lookup
- Storage service creation
- Movie creation and deduplication
"""

logger = logging.getLogger(__name__)

BOGOTA_TZ = zoneinfo.ZoneInfo("America/Bogota")

SPANISH_MONTHS_ABBREVIATIONS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4, "may": 5, "jun": 6,
    "jul": 7, "ago": 8, "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}

# Browser configuration
BROWSER_TIMEOUT_SECONDS = 120


def parse_time_string(time_str: str) -> datetime.time | None:
    """
    Parse time string like '12:50 pm', '4:30 pm', or '2:00 p.m.' to datetime.time.

    Handles both 'am/pm' and 'a.m./p.m.' formats.
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


async def fetch_page_html_async(url: str) -> str:
    """
    Fetch HTML content from a URL using Camoufox headless browser.

    This is a generic page fetcher suitable for simple page loads.
    For pages that require interactions (clicking, selecting dates),
    use a custom async function in your scraper.
    """
    logger.info(f"Scraping page: {url}")

    async with AsyncCamoufox(headless=True) as browser:
        context = await browser.new_context()  # pyright: ignore[reportAttributeAccessIssue]
        page = await context.new_page()

        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=BROWSER_TIMEOUT_SECONDS * 1000,
            )
            html_content = await page.content()
        finally:
            await context.close()

    return html_content


def fetch_page_html(url: str) -> str:
    """Synchronous wrapper to fetch HTML using async Camoufox."""
    return asyncio.run(fetch_page_html_async(url))


@dataclass
class MovieMetadata:
    """
    Metadata extracted from a movie listing source (colombia.com, etc.).

    Each scraper is responsible for parsing their source's date format
    into the standardized release_date and release_year fields.
    """

    genre: str
    duration_minutes: int | None
    classification: str
    director: str
    actors: list[str]
    original_title: str | None
    release_date: datetime.date | None
    release_year: int | None
    trailer_url: str | None = None

@dataclass
class TaskReport:
    """Report of a download task's results."""

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


