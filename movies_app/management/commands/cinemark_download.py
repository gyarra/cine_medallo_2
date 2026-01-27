"""
Manually run the Cinemark showtime scraper.

This is the same task that runs automatically via Celery.
Scrapes showtimes from cinemark.com.co for all theaters with scraper_type="cinemark",
looks up movies on TMDB, and saves showtimes to the database.

Usage:
    python manage.py cinemark_download

Requires:
    - TMDB_API_KEY environment variable for movie metadata lookup
    - Theaters with scraper_type="cinemark" in database
"""

from django.core.management.base import BaseCommand

from movies_app.tasks.cinemark_download_task import cinemark_download_task


class Command(BaseCommand):
    help = "Download movie showtimes from Cinemark theaters"

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        self.stdout.write("Executing cinemark_download_task...\n\n")
        cinemark_download_task()
        self.stdout.write(self.style.SUCCESS("Task completed."))
