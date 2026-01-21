"""
Delete Movie Command

Deletes a movie and all associated showtimes from the database.

Usage:
    python manage.py delete_movie <movie_id>
    python manage.py delete_movie --slug <movie-slug>
    python manage.py delete_movie --tmdb-id <tmdb_id>

Examples:
    # Delete by primary key
    python manage.py delete_movie 42

    # Delete by slug
    python manage.py delete_movie --slug avatar-fuego-y-cenizas

    # Delete by TMDB ID
    python manage.py delete_movie --tmdb-id 123456

    # Skip confirmation prompt
    python manage.py delete_movie 42 --force
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from movies_app.models import Movie, Showtime


class Command(BaseCommand):
    help = "Delete a movie and all its associated showtimes"

    def add_arguments(self, parser):
        parser.add_argument(
            "movie_id",
            nargs="?",
            type=int,
            help="The primary key ID of the movie to delete",
        )
        parser.add_argument(
            "--slug",
            type=str,
            help="Delete movie by slug",
        )
        parser.add_argument(
            "--tmdb-id",
            type=int,
            help="Delete movie by TMDB ID",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Skip confirmation prompt",
        )

    def handle(self, *args, **options):
        movie = self._find_movie(options)
        showtime_count = Showtime.objects.filter(movie=movie).count()

        self.stdout.write(f"\nMovie: {movie}")
        self.stdout.write(f"  ID: {movie.pk}")
        self.stdout.write(f"  Slug: {movie.slug}")
        self.stdout.write(f"  TMDB ID: {movie.tmdb_id}")
        self.stdout.write(f"  Showtimes: {showtime_count}")

        if not options["force"]:
            confirm = input(
                f"\nAre you sure you want to delete this movie and {showtime_count} showtimes? [y/N] "
            )
            if confirm.lower() != "y":
                self.stdout.write(self.style.WARNING("Aborted."))
                return

        with transaction.atomic():
            deleted_showtimes, _ = Showtime.objects.filter(movie=movie).delete()
            movie_title = str(movie)
            movie.delete()

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDeleted movie '{movie_title}' and {deleted_showtimes} showtimes."
            )
        )

    def _find_movie(self, options) -> Movie:
        movie_id = options.get("movie_id")
        slug = options.get("slug")
        tmdb_id = options.get("tmdb_id")

        if sum(bool(x) for x in [movie_id, slug, tmdb_id]) != 1:
            raise CommandError(
                "Provide exactly one of: movie_id, --slug, or --tmdb-id"
            )

        try:
            if movie_id:
                return Movie.objects.get(pk=movie_id)
            elif slug:
                return Movie.objects.get(slug=slug)
            else:
                return Movie.objects.get(tmdb_id=tmdb_id)
        except Movie.DoesNotExist:
            if movie_id:
                raise CommandError(f"Movie with ID {movie_id} not found")
            elif slug:
                raise CommandError(f"Movie with slug '{slug}' not found")
            else:
                raise CommandError(f"Movie with TMDB ID {tmdb_id} not found")
