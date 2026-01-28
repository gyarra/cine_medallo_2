"""
Manually run the Royal Films showtime scraper.

This is the same task that runs automatically via Celery.
Scrapes the cartelera from cinemasroyalfilms.com for each Royal Films theater,
looks up movies on TMDB, and saves showtimes to the database.

Usage:
    python manage.py royal_download

Requires TMDB_API_KEY environment variable for movie metadata lookup.
"""

from django.core.management.base import BaseCommand

from movies_app.tasks.royal_download_task import royal_download_task


class Command(BaseCommand):
    help = "Download movie showtimes from Royal Films (cinemasroyalfilms.com)"

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        self.stdout.write("Executing royal_download_task...")
        royal_download_task()
        self.stdout.write(self.style.SUCCESS("Task completed."))
