from django.db import models


class UnfindableMovieUrl(models.Model):
    """
    Tracks colombia.com movie URLs that could not be matched to TMDB.

    Used to avoid redundant TMDB API calls for movies we've already
    failed to match.
    """

    class Reason(models.TextChoices):
        NO_TMDB_RESULTS = "no_tmdb_results", "No TMDB Results"
        NO_MATCH = "no_match", "No Match Found"
        NO_METADATA = "no_metadata", "Could Not Scrape Metadata"
        MISSING_RELEASE_DATE = "missing_release_date", "Missing Release Date"

    url = models.URLField(unique=True, max_length=500)
    movie_title = models.CharField(max_length=500)
    original_title = models.CharField(max_length=500, default="")
    reason = models.CharField(max_length=50, choices=Reason.choices)
    attempts = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["url"]),
            models.Index(fields=["reason"]),
            models.Index(fields=["last_seen"]),
        ]
        ordering = ["-last_seen"]

    def __str__(self) -> str:
        return f"{self.movie_title} ({self.reason})"
