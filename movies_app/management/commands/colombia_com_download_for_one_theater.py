"""
Scrape showtimes from a theater's colombia.com page, using the download task.

Usage:
    # List theaters with colombia.com URLs configured
    python manage.py colombia_com_download_for_one_theater --list

    # Scrape showtimes and save to database
    python manage.py colombia_com_download_for_one_theater procinal-monterrey-medellin
"""

from django.core.management.base import BaseCommand, CommandError

from movies_app.models import Theater
from movies_app.tasks.colombia_com_download_task import save_showtimes_for_theater


class Command(BaseCommand):
    help = "Scrape showtimes from a theater's colombia.com page and save to database"

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
        self.stdout.write("Scraping showtimes and saving to database...\n\n\n")

        try:
            showtimes_saved = save_showtimes_for_theater(theater)
        except TimeoutError:
            raise CommandError(f"Timeout while scraping {theater.colombia_dot_com_url}")
        except Exception as e:
            raise CommandError(f"Error scraping theater: {e}")

        self.stdout.write(
            self.style.SUCCESS(f"\nSaved {showtimes_saved} showtimes to database")
        )

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
