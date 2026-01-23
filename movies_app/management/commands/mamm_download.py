"""
Manually run the MAMM showtime scraper.

This is the same task that runs automatically via Celery.
Scrapes the weekly schedule from elmamm.org/cine/, looks up movies
on TMDB, and saves showtimes to the database.

Usage:
    python manage.py mamm_download

Requires TMDB_API_KEY environment variable for movie metadata lookup.
"""

from django.core.management.base import BaseCommand

from movies_app.tasks.mamm_download_task import mamm_download_task


class Command(BaseCommand):
    help = "Download movie showtimes from MAMM (elmamm.org)"

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        self.stdout.write("Executing mamm_download_task...")
        mamm_download_task()
        self.stdout.write(self.style.SUCCESS("Task completed."))
