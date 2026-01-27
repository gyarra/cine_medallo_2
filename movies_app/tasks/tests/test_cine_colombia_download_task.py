import datetime
from unittest.mock import MagicMock

import pytest

from movies_app.models import Theater
from movies_app.services.tmdb_service import (
    TMDBGenre,
    TMDBMovieDetails,
    TMDBMovieResult,
    TMDBProductionCompany,
    TMDBSearchResponse,
    TMDBService,
)
from movies_app.tasks.cine_colombia_download_task import (
    CineColombiaScraperAndHTMLParser,
)
from movies_app.tasks.tests.conftest import load_html_snapshot


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def cine_colombia_theater(db):
    """Create a Cine Colombia theater for tests."""
    theater, _ = Theater.objects.get_or_create(
        slug="viva-envigado",
        defaults={
            "name": "Viva Envigado",
            "chain": "Cine Colombia",
            "address": "Carrera 48 # 32B Sur - 139",
            "city": "Envigado",
            "neighborhood": "",
            "website": "https://www.cinecolombia.com",
            "screen_count": 14,
            "is_active": True,
            "scraper_type": "cine_colombia",
            "download_source_url": "https://www.cinecolombia.com/cinemas/viva-envigado/",
            "scraper_config": {},
        },
    )
    return theater


@pytest.fixture
def mock_tmdb_service_for_cine_colombia():
    """Mock TMDB service for Cine Colombia tests."""
    mock_response = TMDBSearchResponse(
        page=1,
        total_pages=1,
        total_results=1,
        results=[
            TMDBMovieResult(
                id=123456,
                title="La Empleada",
                original_title="The Housemaid",
                overview="A woman's story",
                release_date="2026-01-01",
                popularity=100.0,
                vote_average=7.5,
                vote_count=1000,
                poster_path="/housemaid_poster.jpg",
                backdrop_path="/housemaid_backdrop.jpg",
                genre_ids=[27, 53],
                original_language="en",
                adult=False,
                video=False,
            )
        ],
    )

    mock_instance = MagicMock(spec=TMDBService)
    mock_instance.search_movie.return_value = mock_response
    mock_instance.get_movie_details.return_value = TMDBMovieDetails(
        id=123456,
        title="La Empleada",
        original_title="The Housemaid",
        overview="A woman's story",
        release_date="2026-01-01",
        popularity=100.0,
        vote_average=7.5,
        vote_count=1000,
        poster_path="/housemaid_poster.jpg",
        backdrop_path="/housemaid_backdrop.jpg",
        genres=[TMDBGenre(id=27, name="Horror"), TMDBGenre(id=53, name="Thriller")],
        original_language="en",
        adult=False,
        video=False,
        runtime=131,
        budget=10000000,
        revenue=50000000,
        status="Released",
        tagline="Fear comes home",
        homepage="",
        imdb_id="tt1234567",
        production_companies=[
            TMDBProductionCompany(
                id=1,
                name="Test Studio",
                logo_path=None,
                origin_country="US",
            )
        ],
        cast=None,
        crew=None,
        videos=None,
        certification=None,
    )
    return mock_instance


# =============================================================================
# Tests: HTML Parsing for Movies
# =============================================================================


class TestCineColombiaMovieParsing:
    """Tests for parsing movies from Cine Colombia HTML."""

    def test_parse_movies_from_html(self):
        """Parse movies from theater page HTML."""
        html_content = load_html_snapshot("cine_colombia___movies_for_one_theater.html")
        selected_date = datetime.date(2026, 1, 27)

        movies = CineColombiaScraperAndHTMLParser._parse_movies_from_html(
            html_content, selected_date
        )

        assert len(movies) >= 10

        titles = [m.title for m in movies]
        assert "The Housemaid" in titles
        assert "Marty Supreme" in titles
        assert "Zootopia 2" in titles
        assert "Mercy" in titles

    def test_parse_movie_extracts_film_id(self):
        """Verify film IDs are correctly extracted from element IDs."""
        html_content = load_html_snapshot("cine_colombia___movies_for_one_theater.html")
        selected_date = datetime.date(2026, 1, 27)

        movies = CineColombiaScraperAndHTMLParser._parse_movies_from_html(
            html_content, selected_date
        )

        housemaid = next((m for m in movies if "Housemaid" in m.title), None)
        assert housemaid is not None
        assert housemaid.film_id == "ho00000338"

    def test_parse_movie_extracts_url(self):
        """Verify movie URLs are correctly extracted."""
        html_content = load_html_snapshot("cine_colombia___movies_for_one_theater.html")
        selected_date = datetime.date(2026, 1, 27)

        movies = CineColombiaScraperAndHTMLParser._parse_movies_from_html(
            html_content, selected_date
        )

        housemaid = next((m for m in movies if "Housemaid" in m.title), None)
        assert housemaid is not None
        assert "cinecolombia.com/films/the-housemaid" in housemaid.url


# =============================================================================
# Tests: HTML Parsing for Showtimes
# =============================================================================


class TestCineColombiaShowtimeParsing:
    """Tests for parsing showtimes from Cine Colombia HTML."""

    def test_parse_showtimes_extracts_times(self):
        """Verify showtime times are correctly extracted."""
        html_content = load_html_snapshot("cine_colombia___movies_for_one_theater.html")
        selected_date = datetime.date(2026, 1, 27)

        movies = CineColombiaScraperAndHTMLParser._parse_movies_from_html(
            html_content, selected_date
        )

        housemaid = next((m for m in movies if "Housemaid" in m.title), None)
        assert housemaid is not None
        assert len(housemaid.showtimes) > 0

        times = [st.time for st in housemaid.showtimes]
        assert datetime.time(12, 45) in times

    def test_parse_showtimes_extracts_screen(self):
        """Verify screen names are correctly extracted."""
        html_content = load_html_snapshot("cine_colombia___movies_for_one_theater.html")
        selected_date = datetime.date(2026, 1, 27)

        movies = CineColombiaScraperAndHTMLParser._parse_movies_from_html(
            html_content, selected_date
        )

        housemaid = next((m for m in movies if "Housemaid" in m.title), None)
        assert housemaid is not None

        screens = [st.screen for st in housemaid.showtimes]
        assert "SALA 3" in screens

    def test_parse_showtimes_extracts_format(self):
        """Verify format (2D/3D) is correctly extracted."""
        html_content = load_html_snapshot("cine_colombia___movies_for_one_theater.html")
        selected_date = datetime.date(2026, 1, 27)

        movies = CineColombiaScraperAndHTMLParser._parse_movies_from_html(
            html_content, selected_date
        )

        avatar = next((m for m in movies if "Avatar" in m.title), None)
        assert avatar is not None

        formats = [st.format for st in avatar.showtimes]
        assert "3D" in formats

    def test_parse_showtimes_extracts_translation_type(self):
        """Verify translation type (Doblada/Subtitulada) is correctly extracted."""
        html_content = load_html_snapshot("cine_colombia___movies_for_one_theater.html")
        selected_date = datetime.date(2026, 1, 27)

        movies = CineColombiaScraperAndHTMLParser._parse_movies_from_html(
            html_content, selected_date
        )

        marty = next((m for m in movies if "Marty Supreme" in m.title), None)
        assert marty is not None

        translation_types = [st.translation_type for st in marty.showtimes]
        assert "SUB" in translation_types


# =============================================================================
# Tests: Source URL Generation
# =============================================================================


class TestCineColombiaSourceUrlGeneration:
    """Tests for source URL generation."""

    def test_generate_movie_source_url(self):
        """Verify source URL generation."""
        film_id = "ho00000338"
        url = CineColombiaScraperAndHTMLParser.generate_movie_source_url(film_id)
        assert url == "https://www.cinecolombia.com/films/ho00000338"
