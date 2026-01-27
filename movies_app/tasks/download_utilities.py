from __future__ import annotations

import asyncio
import datetime
import logging
import re
import zoneinfo
from dataclasses import dataclass

from camoufox.async_api import AsyncCamoufox

from movies_app.models import OperationalIssue, Showtime

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
BROWSER_TIMEOUT_SECONDS = 20

# Translation type mapping from scraper values to database values
TRANSLATION_TYPE_MAP = {
    # Cineprox values
    "Doblada": Showtime.TranslationType.DOBLADA,
    "Subtitulada": Showtime.TranslationType.SUBTITULADA,
    "doblada": Showtime.TranslationType.DOBLADA,
    "subtitulada": Showtime.TranslationType.SUBTITULADA,
    # Colombia.com values
    "DOBLADA": Showtime.TranslationType.DOBLADA,
    "SUBTITULADA": Showtime.TranslationType.SUBTITULADA,
    # Masculine forms (map to feminine)
    "Doblado": Showtime.TranslationType.DOBLADA,
    "Subtitulado": Showtime.TranslationType.SUBTITULADA,
    "DOBLADO": Showtime.TranslationType.DOBLADA,
    "SUBTITULADO": Showtime.TranslationType.SUBTITULADA,
    "doblado": Showtime.TranslationType.DOBLADA,
    "subtitulado": Showtime.TranslationType.SUBTITULADA,
    # Original language
    "ORIGINAL": Showtime.TranslationType.ORIGINAL,
    "Original": Showtime.TranslationType.ORIGINAL,
    "original": Showtime.TranslationType.ORIGINAL,
    # Empty values
    "": "",
}


def normalize_translation_type(value: str, task: str, context: dict[str, str]) -> str:
    """
    Normalize a translation type value to one of the valid Showtime.TranslationType values.

    Args:
        value: The raw translation type value from the scraper
        task: The task name for OperationalIssue logging
        context: Additional context dict for OperationalIssue (movie, theater, etc.)

    Returns:
        The normalized value (DOBLADA, SUBTITULADA, ORIGINAL, or empty string)
        Returns empty string and logs OperationalIssue for unknown values
    """
    normalized = TRANSLATION_TYPE_MAP.get(value)
    if normalized is not None:
        return normalized

    logger.warning(f"Unknown translation type: '{value}'")
    OperationalIssue.objects.create(
        name="Unknown Translation Type",
        task=task,
        error_message=f"Unknown translation type: '{value}'",
        context=context,
        severity=OperationalIssue.Severity.WARNING,
    )
    return ""


def parse_time_string(time_str: str) -> datetime.time | None:
    """
    Parse time string to datetime.time.

    Handles multiple formats:
    - 12-hour with AM/PM: '12:50 pm', '4:30 pm', '2:00 p.m.'
    - 24-hour: '19:00', '14:30', '09:15'
    """
    time_str = time_str.strip().lower()

    # Try 12-hour format with AM/PM
    match = re.match(r"(\d{1,2}):(\d{2})\s*(a\.?m\.?|p\.?m\.?)", time_str)
    if match:
        hour = int(match.group(1))
        minute = int(match.group(2))
        period = match.group(3).replace(".", "")

        if period == "pm" and hour != 12:
            hour += 12
        elif period == "am" and hour == 12:
            hour = 0

        return datetime.time(hour, minute)

    # Try 24-hour format (HH:MM)
    match_24h = re.match(r"(\d{1,2}):(\d{2})$", time_str)
    if match_24h:
        hour = int(match_24h.group(1))
        minute = int(match_24h.group(2))
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return datetime.time(hour, minute)

    logger.warning(f"Failed to parse time string: '{time_str}'")
    return None


async def fetch_page_html_async(
    url: str,
    wait_selector: str | None = None,
    sleep_seconds_after_wait: float = 0,
) -> str:
    """
    Fetch HTML content from a URL using Camoufox headless browser.

    This is a generic page fetcher suitable for simple page loads.
    For pages that require interactions (clicking, selecting dates),
    use a custom async function in your scraper.

    Args:
        url: The URL to fetch.
        wait_selector: Optional CSS selector to wait for before returning HTML.
            Useful for React/SPA pages that render content after JavaScript executes.
        sleep_seconds_after_wait: Optional delay after page load before capturing HTML.
    """
    logger.info(f"Scraping page: {url}")

    async with AsyncCamoufox(headless=False) as browser:
        context = await browser.new_context()  # pyright: ignore[reportAttributeAccessIssue]
        page = await context.new_page()

        try:
            await page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=BROWSER_TIMEOUT_SECONDS * 1000,
            )

            if wait_selector:
                await page.wait_for_selector(
                    wait_selector,
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )

            if sleep_seconds_after_wait > 0:
                await asyncio.sleep(sleep_seconds_after_wait)

            html_content = await page.content()
        finally:
            await context.close()

    return html_content


def fetch_page_html(
    url: str,
    wait_selector: str | None = None,
    sleep_seconds_after_wait: float = 0,
) -> str:
    """Synchronous wrapper to fetch HTML using async Camoufox."""
    return asyncio.run(fetch_page_html_async(url, wait_selector, sleep_seconds_after_wait))


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


