"""
Scrape showtimes from a single Cine Colombia theater.

Usage:
    # List theaters with cine_colombia scraper configured
    python manage.py cine_colombia_download_for_one_theater --list

    # Scrape showtimes and save to database
    python manage.py cine_colombia_download_for_one_theater viva-envigado
"""

from django.core.management.base import BaseCommand, CommandError

from movies_app.models import Theater
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.cine_colombia_download_task import (
    CineColombiaScraperAndHTMLParser,
    CineColombiaShowtimeSaver,
)


class Command(BaseCommand):
    help = "Scrape showtimes from a single Cine Colombia theater and save to database"

    def add_arguments(self, parser):
        parser.add_argument(
            "theater_slug",
            type=str,
            nargs="?",
            help="Slug of the theater to scrape (e.g., 'viva-envigado')",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List theaters with cine_colombia scraper configured",
        )

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        if options["list"]:
            self._list_theaters()
            return

        theater_slug = options["theater_slug"]
        if not theater_slug:
            raise CommandError(
                "Please provide a theater_slug or use --list to see available theaters"
            )

        try:
            theater = Theater.objects.get(slug=theater_slug)
        except Theater.DoesNotExist:
            raise CommandError(f"No theater found with slug '{theater_slug}'")

        self.stdout.write(f"Found theater: {theater.name}")

        if theater.scraper_type != "cine_colombia":
            raise CommandError(
                f"Theater '{theater.name}' is not configured for cine_colombia scraper "
                f"(scraper_type='{theater.scraper_type}')"
            )

        self.stdout.write(f"Cartelera URL: {theater.download_source_url}")
        self.stdout.write(f"Scraper config: {theater.scraper_config}")
        self.stdout.write("Scraping showtimes and saving to database...\n\n")

        scraper = CineColombiaScraperAndHTMLParser()
        tmdb_service = TMDBService()
        storage_service = SupabaseStorageService.create_from_settings()
        if not storage_service:
            raise CommandError("Failed to create storage service")

        saver = CineColombiaShowtimeSaver(scraper, tmdb_service, storage_service)

        try:
            showtimes_saved = saver.execute_for_theater(theater)
        except Exception as e:
            raise CommandError(f"Error scraping theater: {e}")

        self.stdout.write(
            self.style.SUCCESS(f"\nSaved {showtimes_saved} showtimes to database")
        )

    def _list_theaters(self):
        """List theaters configured for cine_colombia scraper."""
        theaters = Theater.objects.filter(scraper_type="cine_colombia")

        if not theaters:
            self.stdout.write(
                self.style.WARNING(
                    "No theaters found with cine_colombia scraper configured"
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"Cine Colombia theaters ({theaters.count()}):")
        )
        for theater in theaters:
            self.stdout.write(f"  - {theater.slug}: {theater.name}")
            self.stdout.write(f"    URL: {theater.download_source_url}")
