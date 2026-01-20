"""
Manually run the colombia.com showtime scraper for all active theaters.

This is the same task that runs automatically via Celery every 10 minutes.
Scrapes showtimes for today and all available future dates, looks up movies
on TMDB, and saves to the database.

Usage:
    python manage.py colombia_com_run_download_task

Requires TMDB_API_KEY environment variable for movie metadata lookup.
"""

from django.core.management.base import BaseCommand

from movies_app.tasks.colombia_com_download_task import colombia_com_download_task


class Command(BaseCommand):
    help = "Download movie showtime data from colombia.com for all active theaters"

    def handle(self, *args, **options):
        self.stdout.write("Executing colombia_com_download_task...")
        colombia_com_download_task()
        self.stdout.write(self.style.SUCCESS("Task completed."))
