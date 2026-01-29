"""
Cinepolis Scraper Management Command

Manually run the Cinepolis movie and showtime scraper.

USAGE
-----
Run for all theaters:
    python manage.py scrape_cinepolis

Run for a specific theater:
    python manage.py scrape_cinepolis --theater "Cinépolis City Plaza"

EXAMPLES
--------
# Run full scrape (all Cinepolis theaters)
python manage.py scrape_cinepolis

# Test with just one theater
python manage.py scrape_cinepolis --theater "Cinépolis City Plaza"

# Test movie collection only (from home page)
python manage.py scrape_cinepolis --movies-only
"""

import logging

from django.core.management.base import BaseCommand, CommandParser

from movies_app.models import Movie, Theater
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.cinepolis_download_task import (
    CinepolisScraperAndHTMLParser,
    CinepolisShowtimeSaver,
)

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Scrape movies and showtimes from Cinepolis theaters"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--theater",
            type=str,
            help="Name of specific theater to scrape (must match exactly)",
        )
        parser.add_argument(
            "--movies-only",
            action="store_true",
            help="Only scrape movies from home page, don't scrape showtimes",
        )

    def handle(self, *args: object, **options: object) -> None:
        theater_name = options.get("theater")
        movies_only = options.get("movies_only", False)

        scraper = CinepolisScraperAndHTMLParser()
        tmdb_service = TMDBService()
        storage_service = SupabaseStorageService.create_from_settings()

        saver = CinepolisShowtimeSaver(scraper, tmdb_service, storage_service)

        if movies_only:
            self.stdout.write("Scraping movies from Cinepolis home page...")
            movies = saver._find_movies_for_chain()
            self.stdout.write(self.style.SUCCESS(f"Found {len(movies)} movies:"))
            for movie in movies:
                self.stdout.write(f"  - {movie.name}: {movie.source_url}")
            return

        if theater_name:
            theater = Theater.objects.filter(
                name=theater_name,
                scraper_type="cinepolis",
            ).first()

            if not theater:
                self.stderr.write(
                    self.style.ERROR(f"Theater not found: {theater_name}")
                )
                self.stderr.write("Available Cinepolis theaters:")
                for t in Theater.objects.filter(scraper_type="cinepolis"):
                    self.stderr.write(f"  - {t.name}")
                return

            self.stdout.write(f"Scraping theater: {theater.name}...")
            movies_cache: dict[str, Movie | None] = {}

            # First get movies from chain
            movies = saver._find_movies_for_chain()
            saver._get_or_create_movies(movies, movies_cache)

            count = saver._process_theater(theater, movies_cache)
            self.stdout.write(
                self.style.SUCCESS(f"Saved {count} showtimes for {theater.name}")
            )
        else:
            self.stdout.write("Running full Cinepolis scrape...")
            report = saver.execute()
            report.print_report()
            self.stdout.write(self.style.SUCCESS("Scrape complete!"))
