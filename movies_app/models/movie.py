"""
Movie model for storing film information.
"""

from django.db import models


class Movie(models.Model):
    """
    Represents a film that can be shown at theaters.
    """

    title_es = models.CharField(
        max_length=300,
        help_text="Movie title in Spanish",
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

    def __str__(self):
        if self.year:
            return f"{self.title_es} ({self.year})"
        return self.title_es

    @property
    def tmdb_url(self) -> str | None:
        """Get the TMDB URL for this movie."""
        if self.tmdb_id:
            return f"https://www.themoviedb.org/movie/{self.tmdb_id}"
        return None

    @property
    def imdb_url(self) -> str | None:
        """Get the IMDB URL for this movie."""
        if self.imdb_id:
            return f"https://www.imdb.com/title/{self.imdb_id}/"
        return None
