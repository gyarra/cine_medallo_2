"""
Manually run the Royal Films showtime scraper.

This is the same task that runs automatically via Celery.
Scrapes the cartelera from cinemasroyalfilms.com for each Royal Films theater,
looks up movies on TMDB, and saves showtimes to the database.

Usage:
    # Download for all Royal Films theaters
    python manage.py royal_download

    # Download for a single theater by ID
    python manage.py royal_download --theater 5

    # List available Royal Films theaters
    python manage.py royal_download --list

Requires TMDB_API_KEY environment variable for movie metadata lookup.
"""

from django.core.management.base import BaseCommand

from movies_app.models import Theater
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.royal_download_task import RoyalScraperAndHTMLParser, RoyalShowtimeSaver


class Command(BaseCommand):
    help = "Download movie showtimes from Royal Films (cinemasroyalfilms.com)"

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--theater",
            type=int,
            help="Theater ID to download showtimes for (downloads all if not specified)",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List available Royal Films theaters and exit",
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        if options["list"]:
            self._list_theaters()
            return

        scraper = RoyalScraperAndHTMLParser()
        tmdb_service = TMDBService()
        storage_service = SupabaseStorageService.create_from_settings()
        saver = RoyalShowtimeSaver(scraper, tmdb_service, storage_service)

        if options["theater"]:
            self._run_for_single_theater(saver, options["theater"])
        else:
            self._run_for_all_theaters(saver)

    def _list_theaters(self) -> None:
        theaters = Theater.objects.filter(scraper_type="royal").order_by("id")
        if not theaters:
            self.stdout.write(self.style.WARNING("No Royal Films theaters found."))
            return

        self.stdout.write("Available Royal Films theaters:")
        for theater in theaters:
            self.stdout.write(f"  {theater.id}: {theater.name}")  # pyright: ignore[reportAttributeAccessIssue]

    def _run_for_single_theater(self, saver: RoyalShowtimeSaver, theater_id: int) -> None:
        try:
            theater = Theater.objects.get(id=theater_id, scraper_type="royal")
        except Theater.DoesNotExist:
            self.stdout.write(
                self.style.ERROR(f"Theater with ID {theater_id} not found or not a Royal Films theater.")
            )
            self.stdout.write("Use --list to see available theaters.")
            return

        self.stdout.write(f"Executing royal_download_task for {theater.name}...")
        showtimes_count = saver.execute_for_theater(theater)
        self.stdout.write(self.style.SUCCESS(f"Task completed. Saved {showtimes_count} showtimes."))

    def _run_for_all_theaters(self, saver: RoyalShowtimeSaver) -> None:
        self.stdout.write("Executing royal_download_task for all theaters...")
        report = saver.execute()
        report.print_report()
        self.stdout.write(self.style.SUCCESS("Task completed."))
