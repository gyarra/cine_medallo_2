"""
MovieSourceUrl model for storing scraper-specific URLs for movies.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.db import models

if TYPE_CHECKING:
    from movies_app.models import Movie


class MovieSourceUrl(models.Model):
    """
    Stores the URL for a movie from a specific scraper source.

    This allows tracking movies across multiple scrapers without adding
    a separate URL field to the Movie model for each scraper.
    """

    class ScraperType(models.TextChoices):
        COLOMBIA_COM = "colombia_com", "colombia.com"
        MAMM = "mamm", "MAMM (elmamm.org)"
        CINE_COLOMBIA = "cine_colombia", "Cine Colombia"
        COLOMBO_AMERICANO = "colombo_americano", "Colombo Americano"
        PROCINAL = "procinal", "Procinal"
        CINEMARK = "cinemark", "Cinemark"
        ROYAL_FILMS = "royal_films", "Royal Films"
        CINEPROX = "cineprox", "Cineprox"
        CINEPOLIS = "cinepolis", "Cinepolis"

    movie = models.ForeignKey(
        "movies_app.Movie",
        on_delete=models.CASCADE,
        related_name="source_urls",
    )
    scraper_type = models.CharField(
        max_length=50,
        choices=ScraperType.choices,
        help_text="The scraper/source this URL belongs to",
    )
    url = models.URLField(
        max_length=500,
        help_text="URL for this movie on the source website",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Movie Source URL"
        verbose_name_plural = "Movie Source URLs"
        constraints = [
            models.UniqueConstraint(
                fields=["scraper_type", "url"],
                name="unique_scraper_url",
            ),
            models.UniqueConstraint(
                fields=["movie", "scraper_type"],
                name="unique_movie_scraper",
            ),
        ]
        indexes = [
            models.Index(fields=["scraper_type", "url"]),
        ]

    @classmethod
    def get_movie_for_source_url(
        cls, url: str, scraper_type: ScraperType
    ) -> "Movie | None":
        """Get the Movie associated with a source URL, or None if not found."""
        source_url = cls.objects.filter(
            scraper_type=scraper_type,
            url=url,
        ).select_related("movie").first()
        if source_url:
            return source_url.movie
        return None

    def get_scraper_type_display(self) -> str:
        """Return display value for scraper_type (Django auto-generates this)."""
        ...

    def __str__(self) -> str:
        scraper_label = self.get_scraper_type_display()
        return f"{self.movie.title_es} - {scraper_label}"
