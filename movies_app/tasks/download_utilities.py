from __future__ import annotations
from __future__ import annotations
import datetime
import logging
from dataclasses import dataclass



"""
Common utilities for movie download tasks.

This module contains shared functionality used by multiple scrapers
(colombia.com, cine colombia, procinal, etc.) for:
- TMDB movie matching and lookup
- Storage service creation
- Movie creation and deduplication
"""

logger = logging.getLogger(__name__)


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


