"""
Template Method pattern for movie and showtime saving.

This module provides a base class that standardizes the workflow for scraping
movies and showtimes from theater websites. Subclasses implement scraper-specific
logic while inheriting common functionality like:
- Theater iteration with error handling
- Movie deduplication across theaters
- TMDB lookup tracking
- Atomic showtime saving
- Task report generation
"""

from __future__ import annotations

import datetime
import logging
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction

from movies_app.models import Movie, MovieSourceUrl, OperationalIssue, Showtime, Theater
from movies_app.services.movie_lookup_service import MovieLookupService
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.download_utilities import TaskReport

if TYPE_CHECKING:
    from movies_app.tasks.download_utilities import MovieMetadata

logger = logging.getLogger(__name__)


@dataclass
class MovieInfo:
    """Information about a movie found on a theater's listing."""

    name: str
    source_url: str


@dataclass
class ShowtimeData:
    """Generic showtime data ready to save to database."""

    movie: Movie
    date: datetime.date
    time: datetime.time
    format: str
    translation_type: str
    screen: str
    source_url: str


class MovieAndShowtimeSaverTemplate(ABC):
    """
    Abstract base class for scraping movies and showtimes.

    Implements the Template Method pattern where execute() defines the algorithm
    skeleton, and subclasses provide scraper-specific implementations.

    The algorithm:
    1. For each theater, find all movies currently showing
    2. Look up/create movies not already in cache (deduplicates across theaters)
    3. For each theater, scrape showtimes and save them atomically
    """

    def __init__(
        self,
        tmdb_service: TMDBService,
        storage_service: SupabaseStorageService | None,
        source_name: str,
        scraper_type: str,
        scraper_type_enum: MovieSourceUrl.ScraperType,
        task_name: str,
    ):
        self.tmdb_service = tmdb_service
        self.storage_service = storage_service
        self.source_name = source_name
        self.scraper_type = scraper_type
        self.scraper_type_enum = scraper_type_enum
        self.task_name = task_name

        self.lookup_service = MovieLookupService(tmdb_service, storage_service, source_name)
        self.tmdb_calls = 0
        self.new_movies: list[str] = []

    def execute(self) -> TaskReport:
        """
        Main entry point. Finds movies across all theaters, then processes showtimes.

        This is the template method that defines the algorithm skeleton.
        """
        theaters = list(Theater.objects.filter(scraper_type=self.scraper_type))
        total_showtimes = 0
        movies_cache: dict[str, Movie | None] = {}

        for theater in theaters:
            try:
                movies_for_theater = self._find_movies(theater)

                self._get_or_create_movies(movies_for_theater, movies_cache)

                showtimes_count = self._process_showtimes_for_theater(
                    theater, movies_for_theater, movies_cache
                )
                total_showtimes += showtimes_count

            except Exception as e:
                self._handle_theater_error(theater, e)

        return TaskReport(
            total_showtimes=total_showtimes,
            tmdb_calls=self.tmdb_calls,
            new_movies=self.new_movies,
        )

    def execute_for_theater(self, theater: Theater) -> int:
        """Process a single theater. Useful for testing or targeted runs."""
        movies_cache: dict[str, Movie | None] = {}
        movies_for_theater = self._find_movies(theater)
        self._get_or_create_movies(movies_for_theater, movies_cache)
        return self._process_showtimes_for_theater(theater, movies_for_theater, movies_cache)

    @abstractmethod
    def _find_movies(self, theater: Theater) -> list[MovieInfo]:
        """
        Find all movies showing at a theater.

        Returns a list of MovieInfo with name and source_url.
        The source_url is used as the cache key for deduplication.
        """

    @abstractmethod
    def _get_movie_metadata(self, movie_info: MovieInfo) -> MovieMetadata | None:
        """
        Fetch metadata for a movie from the scraper source.

        Called only for movies not already in cache or database.
        """

    @abstractmethod
    def _process_showtimes_for_theater(
        self,
        theater: Theater,
        movies_for_theater: list[MovieInfo],
        movies_cache: dict[str, Movie | None],
    ) -> int:
        """
        Scrape and save showtimes for a theater.

        Use movies_for_theater to iterate over movies and movies_cache to look up Movie objects.
        Call _save_showtimes_for_theater to persist showtimes.

        Returns: Number of showtimes saved.
        """

    def _get_or_create_movies(
        self,
        movies_for_theater: list[MovieInfo],
        movies_cache: dict[str, Movie | None],
    ) -> None:
        """
        Look up or create movies not already in cache.

        Updates movies_cache in place. Tracks TMDB calls and new movies.
        """
        for movie_info in movies_for_theater:
            if movie_info.source_url in movies_cache:
                continue

            existing_movie = MovieSourceUrl.get_movie_for_source_url(
                url=movie_info.source_url,
                scraper_type=self.scraper_type_enum,
            )
            if existing_movie:
                movies_cache[movie_info.source_url] = existing_movie
                continue

            metadata = self._get_movie_metadata(movie_info)
            result = self.lookup_service.get_or_create_movie(
                movie_name=movie_info.name,
                source_url=movie_info.source_url,
                scraper_type=self.scraper_type_enum,
                metadata=metadata,
            )

            movies_cache[movie_info.source_url] = result.movie
            if result.tmdb_called:
                self.tmdb_calls += 1
            if result.is_new and result.movie:
                self.new_movies.append(result.movie.title_es)

    @transaction.atomic
    def _save_showtimes_for_theater(
        self,
        theater: Theater,
        showtimes: list[ShowtimeData],
    ) -> int:
        """
        Atomic delete and insert of showtimes for a theater.

        Deletes all existing showtimes for theater, then inserts new ones.
        """
        deleted_count, _ = Showtime.objects.filter(theater=theater).delete()
        if deleted_count:
            logger.info(f"Deleted {deleted_count} existing showtimes for {theater.name}")

        for showtime in showtimes:
            Showtime.objects.create(
                theater=theater,
                movie=showtime.movie,
                start_date=showtime.date,
                start_time=showtime.time,
                format=showtime.format,
                translation_type=showtime.translation_type,
                screen=showtime.screen,
                source_url=showtime.source_url,
            )

        logger.info(f"Saved {len(showtimes)} showtimes for {theater.name}")
        return len(showtimes)

    def _handle_theater_error(self, theater: Theater, error: Exception) -> None:
        """Log error and create OperationalIssue."""
        logger.error(f"Failed to process theater {theater.name}: {error}")
        OperationalIssue.objects.create(
            name=f"{self.source_name.title()} Theater Processing Failed",
            task=self.task_name,
            error_message=str(error),
            traceback=traceback.format_exc(),
            context={"theater_name": theater.name, "theater_slug": theater.slug},
            severity=OperationalIssue.Severity.ERROR,
        )
