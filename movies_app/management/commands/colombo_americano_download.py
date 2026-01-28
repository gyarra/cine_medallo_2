"""
Manually run the Colombo Americano showtime scraper.

This is the same task that runs automatically via Celery.
Scrapes the weekly schedule from colombomedellin.edu.co/programacion-por-salas/,
looks up movies on TMDB, and saves showtimes to the database.

Usage:
    python manage.py colombo_americano_download

Requires TMDB_API_KEY environment variable for movie metadata lookup.
"""

from django.core.management.base import BaseCommand

from movies_app.tasks.colombo_americano_download_task import colombo_americano_download_task


class Command(BaseCommand):
    help = "Download movie showtimes from Colombo Americano (colombomedellin.edu.co)"

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        self.stdout.write("Executing colombo_americano_download_task...")
        colombo_americano_download_task()
        self.stdout.write(self.style.SUCCESS("Task completed."))
