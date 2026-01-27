"""
Manually run the Cine Colombia showtime scraper.

This is the same task that runs automatically via Celery.
Scrapes showtimes from cinecolombia.com for all theaters with scraper_type="cine_colombia",
looks up movies on TMDB, and saves showtimes to the database.

Usage:
    python manage.py cine_colombia_download

Requires:
    - TMDB_API_KEY environment variable for movie metadata lookup
    - Theaters with scraper_type="cine_colombia" in database
"""

from django.core.management.base import BaseCommand

from movies_app.tasks.cine_colombia_download_task import cine_colombia_download_task


class Command(BaseCommand):
    help = "Download movie showtimes from Cine Colombia theaters"

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        self.stdout.write("Executing cine_colombia_download_task...\n\n")
        cine_colombia_download_task()
        self.stdout.write(self.style.SUCCESS("Task completed."))
