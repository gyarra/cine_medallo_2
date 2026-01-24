from django.db import models

from movies_app.models.movie import Movie
from movies_app.models.theater import Theater


class Showtime(models.Model):
    """Represents a specific showing of a movie at a theater."""

    theater = models.ForeignKey(
        Theater,
        on_delete=models.CASCADE,
        related_name="showtimes",
    )
    movie = models.ForeignKey(
        Movie,
        on_delete=models.CASCADE,
        related_name="showtimes",
    )
    start_date = models.DateField()
    start_time = models.TimeField()

    format = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Screening format (e.g., '2D', '3D', 'IMAX', 'XD')",
    )
    # TODO: name this translation_type or similar. Add a different field for original language. This field name is confusing.
    language = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Audio language (e.g., 'DOBLADA', 'SUBTITULADA', 'Original')",
    )
    screen = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Screen/sala identifier",
    )
    source_url = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="URL where this showtime was scraped from",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["start_date"]),
            models.Index(fields=["theater", "start_date"]),
            models.Index(fields=["movie", "start_date"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["theater", "movie", "start_date", "start_time"],
                name="unique_showtime",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.movie.title_es} at {self.theater.name} - {self.start_date} {self.start_time}"
