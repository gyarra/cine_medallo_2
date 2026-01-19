"""
Movie model for storing film information.
"""

from __future__ import annotations

from decimal import Decimal
from typing import TYPE_CHECKING

from django.db import models
from django.utils.text import slugify

if TYPE_CHECKING:
    from movies_app.services.tmdb_service import TMDBMovieResult


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
    age_rating = models.CharField(
        max_length=10,
        blank=True,
        default="",
        help_text="Age rating (e.g., 'PG-13', 'R', '+15')",
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
    def create_from_tmdb(cls, tmdb_result: TMDBMovieResult, poster_size: str = "w500") -> Movie:
        """
        Create a Movie instance from a TMDB search result.

        Args:
            tmdb_result: A TMDBMovieResult from the TMDB API
            poster_size: Image size for poster URL (w92, w154, w185, w342, w500, w780, original)

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

        # Build poster URL
        poster_url = ""
        if tmdb_result.poster_path:
            poster_url = f"https://image.tmdb.org/t/p/{poster_size}{tmdb_result.poster_path}"

        movie = cls.objects.create(
            title_es=tmdb_result.title,
            original_title=tmdb_result.original_title,
            year=year,
            synopsis=tmdb_result.overview,
            poster_url=poster_url,
            tmdb_id=tmdb_result.id,
            tmdb_rating=Decimal(str(tmdb_result.vote_average)) if tmdb_result.vote_average else None,
        )

        return movie

    @classmethod
    def get_or_create_from_tmdb(cls, tmdb_result: TMDBMovieResult, poster_size: str = "w500") -> tuple[Movie, bool]:
        """
        Get existing movie by tmdb_id or create a new one from TMDB result.

        Args:
            tmdb_result: A TMDBMovieResult from the TMDB API
            poster_size: Image size for poster URL

        Returns:
            Tuple of (Movie instance, created boolean)
        """
        try:
            movie = cls.objects.get(tmdb_id=tmdb_result.id)
            return movie, False
        except cls.DoesNotExist:
            movie = cls.create_from_tmdb(tmdb_result, poster_size)
            return movie, True
