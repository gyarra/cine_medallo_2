"""
Scrape showtimes from a single Cineprox theater.

Usage:
    # List theaters with cineprox scraper configured
    python manage.py cineprox_download_for_one_theater --list

    # Scrape showtimes and save to database
    python manage.py cineprox_download_for_one_theater procinal-parque-fabricato-bello
"""

from django.core.management.base import BaseCommand, CommandError

from movies_app.models import Theater
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.cineprox_download_task import (
    CineproxScraperAndHTMLParser,
    CineproxShowtimeSaver,
)


class Command(BaseCommand):
    help = "Scrape showtimes from a single Cineprox theater and save to database"

    def add_arguments(self, parser):
        parser.add_argument(
            "theater_slug",
            type=str,
            nargs="?",
            help="Slug of the theater to scrape (e.g., 'procinal-parque-fabricato-bello')",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List theaters with cineprox scraper configured",
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

        if theater.scraper_type != "cineprox":
            raise CommandError(
                f"Theater '{theater.name}' is not configured for cineprox scraper "
                f"(scraper_type='{theater.scraper_type}')"
            )

        if not theater.scraper_config:
            raise CommandError(
                f"Theater '{theater.name}' has no scraper_config configured"
            )

        self.stdout.write(f"Cartelera URL: {theater.download_source_url}")
        self.stdout.write(f"Scraper config: {theater.scraper_config}")
        self.stdout.write("Scraping showtimes and saving to database...\n\n")

        scraper = CineproxScraperAndHTMLParser()
        tmdb_service = TMDBService()
        storage_service = SupabaseStorageService.create_from_settings()
        if not storage_service:
            raise CommandError("Failed to create storage service")

        saver = CineproxShowtimeSaver(scraper, tmdb_service, storage_service)

        try:
            showtimes_saved = saver.execute_for_theater(theater)
        except Exception as e:
            raise CommandError(f"Error scraping theater: {e}")

        self.stdout.write(
            self.style.SUCCESS(f"\nSaved {showtimes_saved} showtimes to database")
        )

    def _list_theaters(self):
        """List theaters configured for cineprox scraper."""
        theaters = Theater.objects.filter(scraper_type="cineprox")

        if not theaters:
            self.stdout.write(
                self.style.WARNING("No theaters found with cineprox scraper configured")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"Cineprox theaters ({theaters.count()}):")
        )
        for theater in theaters:
            config_status = "✓" if theater.scraper_config else "✗ (missing config)"
            self.stdout.write(f"  {theater.slug}: {theater.name} {config_status}")
