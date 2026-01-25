"""
Manually run the Cineprox showtime scraper.

This is the same task that runs automatically via Celery.
Scrapes showtimes from cineprox.com for all theaters with scraper_type="cineprox",
looks up movies on TMDB, and saves showtimes to the database.

Usage:
    python manage.py cineprox_download

Requires:
    - TMDB_API_KEY environment variable for movie metadata lookup
    - Theaters with scraper_type="cineprox" and scraper_config set in database
"""

from django.core.management.base import BaseCommand

from movies_app.tasks.cineprox_download_task import cineprox_download_task


class Command(BaseCommand):
    help = "Download movie showtimes from Cineprox theaters"

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        self.stdout.write("Executing cineprox_download_task...")
        cineprox_download_task()
        self.stdout.write(self.style.SUCCESS("Task completed."))
