"""
Import a movie from TMDB into the database.

Usage:
    python manage.py import_movie_from_tmdb "Avatar: Fuego Y Cenizas"
    python manage.py import_movie_from_tmdb "Avatar" --year 2025
    python manage.py import_movie_from_tmdb "Fight Club" --language en-US
"""

from django.core.management.base import BaseCommand

from movies_app.models import Movie
from movies_app.services.tmdb_service import TMDBService, TMDBServiceError


class Command(BaseCommand):
    help = "Import a movie from TMDB (The Movie Database) into the database"

    def add_arguments(self, parser):
        parser.add_argument(
            "movie_name",
            type=str,
            help="The movie name to search for",
        )
        parser.add_argument(
            "--year",
            type=int,
            help="Filter by release year",
        )
        parser.add_argument(
            "--language",
            type=str,
            default="es-ES",
            help="Language for results (default: es-ES for Spanish)",
        )
        parser.add_argument(
            "--select",
            type=int,
            help="Automatically select result by index (1-based). If not provided, will prompt.",
        )

    def handle(self, *args, **options):
        movie_name = options["movie_name"]
        year = options["year"]
        language = options["language"]
        select = options["select"]

        self.stdout.write(f"Searching TMDB for: '{movie_name}'")

        try:
            service = TMDBService()
            response = service.search_movie(
                query=movie_name,
                language=language,
                year=year,
            )
        except TMDBServiceError as e:
            self.stderr.write(self.style.ERROR(f"Error: {e}"))
            return

        if response.total_results == 0:
            self.stdout.write(self.style.WARNING("No movies found."))
            return

        # Display results
        self.stdout.write(f"\nFound {response.total_results} result(s):\n")
        for i, movie in enumerate(response.results[:10], 1):
            year_str = f" ({movie.release_date[:4]})" if movie.release_date else ""
            self.stdout.write(f"  {i}. {movie.title}{year_str} [TMDB ID: {movie.id}]")

        # Select movie
        if select:
            selected_index = select - 1
        else:
            self.stdout.write("")
            try:
                choice = input("Select a movie (1-10) or 'q' to quit: ").strip()
                if choice.lower() == "q":
                    self.stdout.write("Cancelled.")
                    return
                selected_index = int(choice) - 1
            except (ValueError, EOFError):
                self.stderr.write(self.style.ERROR("Invalid selection."))
                return

        if selected_index < 0 or selected_index >= len(response.results):
            self.stderr.write(self.style.ERROR("Invalid selection."))
            return

        selected_movie = response.results[selected_index]

        # Check if movie already exists
        existing = Movie.objects.filter(tmdb_id=selected_movie.id).first()
        if existing:
            self.stdout.write(
                self.style.WARNING(f"\nMovie already exists in database: {existing} (ID: {existing.id})")
            )
            return

        # Create the movie
        movie = Movie.create_from_tmdb(selected_movie)

        self.stdout.write(self.style.SUCCESS(f"\nSuccessfully imported: {movie}"))
        self.stdout.write(f"  Database ID: {movie.id}")
        self.stdout.write(f"  TMDB ID: {movie.tmdb_id}")
        self.stdout.write(f"  Original Title: {movie.original_title}")
        self.stdout.write(f"  Year: {movie.year}")
        self.stdout.write(f"  Rating: {movie.tmdb_rating}/10")
        if movie.poster_url:
            self.stdout.write(f"  Poster: {movie.poster_url}")
        if movie.synopsis:
            synopsis = movie.synopsis[:150] + "..." if len(movie.synopsis) > 150 else movie.synopsis
            self.stdout.write(f"  Synopsis: {synopsis}")
