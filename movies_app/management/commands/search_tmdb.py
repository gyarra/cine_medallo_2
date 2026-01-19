"""
Search TMDB for movie information.

Usage:
    python manage.py search_tmdb "Avatar: Fuego Y Cenizas"
    python manage.py search_tmdb "Avatar" --year 2024
    python manage.py search_tmdb "Fight Club" --language en-US
"""

from django.core.management.base import BaseCommand

from movies_app.services.tmdb_service import TMDBService, TMDBServiceError


class Command(BaseCommand):
    help = "Search TMDB (The Movie Database) for movie information"

    def add_arguments(self, parser):
        parser.add_argument(
            "movie_name",
            type=str,
            help="The movie name to search for (in Spanish by default)",
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
            "--limit",
            type=int,
            default=5,
            help="Maximum number of results to display (default: 5)",
        )

    def handle(self, *args, **options):
        movie_name = options["movie_name"]
        year = options["year"]
        language = options["language"]
        limit = options["limit"]

        self.stdout.write(f"Searching TMDB for: '{movie_name}'")
        if year:
            self.stdout.write(f"  Year filter: {year}")
        self.stdout.write(f"  Language: {language}")
        self.stdout.write("")

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

        self.stdout.write(
            self.style.SUCCESS(
                f"Found {response.total_results} result(s) "
                f"(showing {min(limit, len(response.results))})"
            )
        )
        self.stdout.write("")

        for i, movie in enumerate(response.results[:limit], 1):
            self.stdout.write(self.style.HTTP_INFO(f"--- Result {i} ---"))
            self.stdout.write(f"  Title: {movie.title}")
            if movie.original_title != movie.title:
                self.stdout.write(f"  Original Title: {movie.original_title}")
            self.stdout.write(f"  TMDB ID: {movie.id}")
            self.stdout.write(f"  Release Date: {movie.release_date or 'Unknown'}")
            self.stdout.write(f"  Rating: {movie.vote_average}/10 ({movie.vote_count} votes)")
            self.stdout.write(f"  Popularity: {movie.popularity}")
            if movie.overview:
                overview = movie.overview[:200] + "..." if len(movie.overview) > 200 else movie.overview
                self.stdout.write(f"  Overview: {overview}")
            if movie.poster_path:
                self.stdout.write(f"  Poster: {service.get_poster_url(movie.poster_path)}")
            self.stdout.write("")
