"""
Download movie showtimes from MAMM (Museo de Arte Moderno de Medellín).

This command scrapes the weekly schedule from https://www.elmamm.org/cine/
and creates Movie and Showtime records in the database.

Usage:
    python manage.py mamm_download

    # From file (for testing):
    python manage.py mamm_download --file path/to/snapshot.html

Examples:
    # Scrape live MAMM website:
    python manage.py mamm_download

    # Use local HTML file for testing:
    python manage.py mamm_download --file movies_app/tasks/tests/html_snapshot/elmamm_org_semana

    # Show verbose output:
    python manage.py mamm_download --verbosity 2
"""

from django.core.management.base import BaseCommand

from movies_app.tasks.mamm_download_task import (
    _fetch_html,
    MAMM_CINE_URL,
    save_showtimes_from_html,
)


class Command(BaseCommand):
    help = "Download movie showtimes from MAMM (elmamm.org)"

    def add_arguments(self, parser):  # type: ignore[no-untyped-def]
        parser.add_argument(
            "--file",
            type=str,
            help="Path to local HTML file instead of fetching from the web",
        )

    def handle(self, *args, **options) -> str | None:  # type: ignore[no-untyped-def]
        file_path: str | None = options.get("file")

        if file_path:
            self.stdout.write(f"Loading HTML from file: {file_path}")
            with open(file_path, encoding="utf-8") as f:
                html_content = f.read()
        else:
            self.stdout.write("Fetching MAMM schedule from web...")
            html_content = _fetch_html(MAMM_CINE_URL)

        report = save_showtimes_from_html(html_content)

        self.stdout.write(
            self.style.SUCCESS(
                f"Done. Showtimes: {report.total_showtimes}, "
                f"TMDB calls: {report.tmdb_calls}, "
                f"New movies: {len(report.new_movies)}"
            )
        )

        if report.new_movies:
            self.stdout.write("New movies added:")
            for movie_title in report.new_movies:
                self.stdout.write(f"  - {movie_title}")

        return None
