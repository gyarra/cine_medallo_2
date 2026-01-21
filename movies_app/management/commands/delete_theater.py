"""
Delete Theater Command

Deletes a theater and all associated showtimes from the database.

Usage:
    python manage.py delete_theater <theater_id>
    python manage.py delete_theater --slug <theater-slug>

Examples:
    # Delete by primary key
    python manage.py delete_theater 5

    # Delete by slug
    python manage.py delete_theater --slug procinal-monterrey-medellin

    # Skip confirmation prompt
    python manage.py delete_theater 5 --force
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from movies_app.models import Showtime, Theater


class Command(BaseCommand):
    help = "Delete a theater and all its associated showtimes"

    def add_arguments(self, parser):
        parser.add_argument(
            "theater_id",
            nargs="?",
            type=int,
            help="The primary key ID of the theater to delete",
        )
        parser.add_argument(
            "--slug",
            type=str,
            help="Delete theater by slug",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip confirmation prompt",
        )

    def handle(self, *args, **options):
        theater = self._find_theater(options)
        showtime_count = Showtime.objects.filter(theater=theater).count()

        self.stdout.write(f"\nTheater: {theater}")
        self.stdout.write(f"  ID: {theater.pk}")
        self.stdout.write(f"  Slug: {theater.slug}")
        self.stdout.write(f"  Chain: {theater.chain or 'N/A'}")
        self.stdout.write(f"  Address: {theater.address}")
        self.stdout.write(f"  Showtimes: {showtime_count}")

        if not options["force"]:
            confirm = input(
                f"\nAre you sure you want to delete this theater and {showtime_count} showtimes? [y/N] "
            )
            if confirm.lower() != "y":
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        with transaction.atomic():
            deleted_showtimes, _ = Showtime.objects.filter(theater=theater).delete()
            theater_name = str(theater)
            theater.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDeleted '{theater_name}' and {deleted_showtimes} showtimes."
            )
        )

    def _find_theater(self, options) -> Theater:
        theater_id = options.get("theater_id")
        slug = options.get("slug")

        if not theater_id and not slug:
            raise CommandError("You must provide either a theater ID or --slug")

        if theater_id and slug:
            raise CommandError("Provide only one: theater ID or --slug, not both")

        if theater_id:
            try:
                return Theater.objects.get(pk=theater_id)
            except Theater.DoesNotExist:
                raise CommandError(f"Theater with ID {theater_id} not found")

        if slug:
            try:
                return Theater.objects.get(slug=slug)
            except Theater.DoesNotExist:
                raise CommandError(f"Theater with slug '{slug}' not found")

        raise CommandError("Unable to find theater")
