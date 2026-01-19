"""
Management command to scrape movies from a theater's colombia.com page.
"""

from django.core.management.base import BaseCommand, CommandError

from movies_app.models import Theater
from movies_app.tasks.download_from_colombia_dot_com import scrape_theater_movies


class Command(BaseCommand):
    help = "Scrape movie names from a theater's colombia.com page using Camoufox"

    def add_arguments(self, parser):
        parser.add_argument(
            "theater_slug",
            type=str,
            nargs="?",
            help="Slug of the theater to scrape (e.g., 'procinal-monterrey-medellin')",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List the first 10 theaters with colombia_dot_com_url",
        )

    def handle(self, *args, **options):
        if options["list"]:
            self._list_theaters()
            return

        theater_slug = options["theater_slug"]
        if not theater_slug:
            raise CommandError(
                "Please provide a theater_slug or use --list to see available theaters"
            )

        # Find theater by slug
        try:
            theater = Theater.objects.get(slug=theater_slug)
        except Theater.DoesNotExist:
            raise CommandError(f"No theater found with slug '{theater_slug}'")

        self.stdout.write(f"Found theater: {theater.name}")

        if not theater.colombia_dot_com_url:
            raise CommandError(
                f"Theater '{theater.name}' has no colombia_dot_com_url configured"
            )

        self.stdout.write(f"URL: {theater.colombia_dot_com_url}")
        self.stdout.write("Scraping movies with Camoufox...")

        try:
            movie_names = scrape_theater_movies(theater)
        except TimeoutError:
            raise CommandError(f"Timeout while scraping {theater.colombia_dot_com_url}")
        except Exception as e:
            raise CommandError(f"Error scraping theater: {e}")

        self.stdout.write(
            self.style.SUCCESS(f"\nFound {len(movie_names)} movies:")
        )
        for i, name in enumerate(movie_names, 1):
            self.stdout.write(f"  {i}. {name}")

    def _list_theaters(self):
        """List the first 10 theaters that have a colombia_dot_com_url."""
        theaters = Theater.objects.exclude(colombia_dot_com_url__isnull=True).exclude(
            colombia_dot_com_url=""
        )[:10]

        if not theaters:
            self.stdout.write(
                self.style.WARNING("No theaters found with colombia_dot_com_url")
            )
            return

        self.stdout.write(
            self.style.SUCCESS(f"Theaters with colombia_dot_com_url ({len(theaters)}):")
        )
        for theater in theaters:
            self.stdout.write(f"  {theater.slug}: {theater.name}")
