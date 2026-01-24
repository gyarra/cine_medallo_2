"""
Movie model for storing film information.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models
from django.utils.text import slugify

if TYPE_CHECKING:
    from movies_app.services.supabase_storage_service import SupabaseStorageService
    from movies_app.services.tmdb_service import TMDBMovieDetails, TMDBMovieResult, TMDBService

logger = logging.getLogger(__name__)


class Movie(models.Model):
    """
    Represents a film that can be shown at theaters.
    """

    title_es = models.CharField(
        max_length=300,
        help_text="Movie title in Spanish",
    )
    slug = models.SlugField(
        max_length=350,
        unique=True,
        help_text="URL-friendly identifier",
    )
    original_title = models.CharField(
        max_length=300,
        blank=True,
        default="",
        help_text="Original language title",
    )
    year = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Release year",
    )
    duration_minutes = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Runtime in minutes",
    )
    genre = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Primary genre(s)",
    )
    age_rating_colombia = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="Colombian age rating from TMDB (e.g., '+12', '+15', '+18')",
    )
    synopsis = models.TextField(
        blank=True,
        default="",
        help_text="Movie description/plot summary",
    )
    poster_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="URL to movie poster image",
    )
    imdb_id = models.CharField(
        max_length=20,
        blank=True,
        null=True,
        unique=True,
        help_text="IMDB identifier (e.g., 'tt27543632')",
    )
    tmdb_id = models.PositiveIntegerField(
        null=True,
        blank=True,
        unique=True,
        help_text="The Movie Database (TMDB) identifier",
    )
    tmdb_rating = models.DecimalField(
        max_digits=3,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="TMDB user rating (0.0-10.0)",
    )
    colombia_dot_com_url = models.URLField(
        max_length=500,
        null=True,
        blank=True,
        unique=True,
        help_text="URL on colombia.com for this movie",
    )
    trailer_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="YouTube trailer URL",
    )
    backdrop_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="URL to movie backdrop image",
    )
    director = models.CharField(
        max_length=200,
        blank=True,
        default="",
        help_text="Director name(s)",
    )
    cast_summary = models.CharField(
        max_length=500,
        blank=True,
        default="",
        help_text="Top billed actors, comma-separated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-year", "title_es"]
        indexes = [
            models.Index(fields=["title_es"]),
            models.Index(fields=["year"]),
        ]

    def save(self, *args, **kwargs):
        if not self.slug:
            base_slug = slugify(self.title_es)
            slug = base_slug
            counter = 1
            while Movie.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug = f"{base_slug}-{counter}"
                counter += 1
            self.slug = slug
        super().save(*args, **kwargs)

    def __str__(self):
        if self.year:
            return f"{self.title_es} ({self.year})"
        return self.title_es

    @property
    def tmdb_url(self) -> str | None:
        if self.tmdb_id:
            return f"https://www.themoviedb.org/movie/{self.tmdb_id}?language=es-MX"
        return None

    @property
    def imdb_url(self) -> str | None:
        """Get the IMDB URL for this movie."""
        if self.imdb_id:
            return f"https://www.imdb.com/title/{self.imdb_id}/"
        return None

    @classmethod
    def create_from_tmdb(
        cls,
        tmdb_result: TMDBMovieResult,
        tmdb_service: TMDBService | None,
        storage_service: SupabaseStorageService | None,
        title_override: str | None,
    ) -> Movie:
        """
        Create a Movie instance from a TMDB search result.

        If tmdb_service is provided, fetches full movie details including
        runtime, genres, director, cast, and trailer.

        If storage_service is provided, uploads images to Supabase and stores
        those URLs instead of TMDB URLs.

        Args:
            tmdb_result: A TMDBMovieResult from the TMDB API
            tmdb_service: Optional TMDBService for fetching full details
            storage_service: Optional SupabaseStorageService for uploading images
            title_override: Optional title to use instead of TMDB title (e.g., from scraped listing)

        Returns:
            A new saved Movie instance
        """
        # Extract year from release_date (format: "YYYY-MM-DD")
        year = None
        if tmdb_result.release_date:
            try:
                year = int(tmdb_result.release_date.split("-")[0])
            except (ValueError, IndexError):
                pass

        # Build poster URL (will be replaced with Supabase URL if storage_service provided)
        poster_url = ""
        if tmdb_result.poster_path:
            tmdb_poster_url = f"https://image.tmdb.org/t/p/original{tmdb_result.poster_path}"
            poster_url = cls._upload_image_or_fallback(
                storage_service,
                tmdb_poster_url,
                f"posters/{tmdb_result.id}.jpg",
            )

        # Base movie data from search result
        # Use title_override (from scraper) if provided, otherwise use TMDB title
        movie_data = {
            "title_es": title_override or tmdb_result.title,
            "original_title": tmdb_result.original_title,
            "year": year,
            "synopsis": tmdb_result.overview,
            "poster_url": poster_url,
            "tmdb_id": tmdb_result.id,
            "tmdb_rating": Decimal(str(tmdb_result.vote_average)) if tmdb_result.vote_average else None,
        }

        # Fetch full details if service is provided
        if tmdb_service:
            movie_data = cls._enrich_with_tmdb_details(
                movie_data,
                tmdb_result.id,
                tmdb_service,
                storage_service,
            )

        movie = cls.objects.create(**movie_data)
        return movie

    @classmethod
    def _upload_image_or_fallback(
        cls,
        storage_service: SupabaseStorageService | None,
        tmdb_url: str,
        dest_path: str,
    ) -> str:
        """
        Upload image to Supabase if storage service provided, otherwise return TMDB URL.

        Falls back to TMDB URL if upload fails.
        """
        if not storage_service:
            return tmdb_url

        from movies_app.services.supabase_storage_service import SupabaseStorageError

        try:
            # Check if already uploaded
            existing_url = storage_service.get_existing_url(dest_path)
            if existing_url:
                return existing_url
            return storage_service.download_and_upload_from_url(tmdb_url, dest_path)
        except SupabaseStorageError as e:
            logger.warning(f"Failed to upload image to Supabase, using TMDB URL: {e}")
            return tmdb_url

    @classmethod
    def _enrich_with_tmdb_details(
        cls,
        movie_data: dict,
        tmdb_id: int,
        tmdb_service: TMDBService,
        storage_service: SupabaseStorageService | None,
    ) -> dict:
        """
        Enrich movie data with full TMDB details.

        Fetches runtime, genres, director, cast, trailer, and backdrop.
        """
        try:
            details = tmdb_service.get_movie_details(
                tmdb_id,
                include_credits=True,
                include_videos=True,
                include_release_dates=True,
            )
            movie_data = cls._apply_tmdb_details(movie_data, details, storage_service)
        except Exception as e:
            logger.warning(f"Failed to fetch TMDB details for movie {tmdb_id}: {e}")

        return movie_data

    @classmethod
    def _apply_tmdb_details(
        cls,
        movie_data: dict,
        details: TMDBMovieDetails,
        storage_service: SupabaseStorageService | None,
    ) -> dict:
        """Apply TMDBMovieDetails to movie data dict."""
        # Runtime
        if details.runtime:
            movie_data["duration_minutes"] = details.runtime

        # IMDb ID
        if details.imdb_id:
            movie_data["imdb_id"] = details.imdb_id

        # Genres (Spanish names, comma-separated)
        if details.genres:
            movie_data["genre"] = ", ".join(g.name for g in details.genres[:3])

        # Director
        directors = details.directors
        if directors:
            movie_data["director"] = ", ".join(d.name for d in directors[:2])

        # Top cast
        if details.cast:
            top_cast = details.cast[:5]
            movie_data["cast_summary"] = ", ".join(c.name for c in top_cast)

        # Backdrop URL
        if details.backdrop_path:
            tmdb_id = movie_data.get("tmdb_id")
            tmdb_backdrop_url = f"https://image.tmdb.org/t/p/original{details.backdrop_path}"
            movie_data["backdrop_url"] = cls._upload_image_or_fallback(
                storage_service,
                tmdb_backdrop_url,
                f"backdrops/{tmdb_id}.jpg",
            )

        # Trailer URL (prefer Spanish)
        best_trailer = details.get_best_trailer()
        if best_trailer and best_trailer.youtube_url:
            movie_data["trailer_url"] = best_trailer.youtube_url

        # Colombian age rating (certification)
        if details.certification:
            movie_data["age_rating_colombia"] = details.certification

        return movie_data

    @classmethod
    def get_or_create_from_tmdb(
        cls,
        tmdb_result: TMDBMovieResult,
        tmdb_service: TMDBService | None,
        storage_service: SupabaseStorageService | None,
        title_override: str | None,
    ) -> tuple[Movie, bool]:
        """
        Get existing movie by tmdb_id or create a new one from TMDB result.

        Args:
            tmdb_result: A TMDBMovieResult from the TMDB API
            tmdb_service: Optional TMDBService for fetching full details
            storage_service: Optional SupabaseStorageService for uploading images
            title_override: Optional title to use instead of TMDB title (e.g., from scraped listing)

        Returns:
            Tuple of (Movie instance, created boolean)
        """
        try:
            movie = cls.objects.get(tmdb_id=tmdb_result.id)
            return movie, False
        except cls.DoesNotExist:
            movie = cls.create_from_tmdb(
                tmdb_result, tmdb_service, storage_service, title_override=title_override
            )
            return movie, True
