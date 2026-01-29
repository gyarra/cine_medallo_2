import datetime
from unittest.mock import MagicMock

import pytest

from movies_app.models import OperationalIssue, Theater
from movies_app.services.tmdb_service import (
    TMDBGenre,
    TMDBMovieDetails,
    TMDBMovieResult,
    TMDBProductionCompany,
    TMDBSearchResponse,
    TMDBService,
)
from movies_app.tasks.cine_colombia_download_task import (
    CineColombiaMovie,
    CineColombiaScraperAndHTMLParser,
    CineColombiaShowtimeSaver,
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


@pytest.fixture
def mock_storage_service_for_cine_colombia():
    """Mock storage service for Cine Colombia tests."""
    return MagicMock()


# =============================================================================
# Tests: Films Page HTML Parsing
# =============================================================================


class TestCineColombiaFilmsPageParsing:
    """Tests for parsing movies from the Cine Colombia films page."""

    def test_parse_movies_from_films_page(self):
        """Parse movies from the films page HTML."""
        html_content = load_html_snapshot("cine_colombia___all_movies.html")

        movies = CineColombiaScraperAndHTMLParser.parse_movies_from_films_page(html_content)

        assert len(movies) >= 15

        titles = [m.title for m in movies]
        assert "La Empleada" in titles
        assert "Marty Supreme" in titles
        assert "Zootopia 2" in titles
        assert "Sin Piedad" in titles

    def test_parse_movies_extracts_film_id(self):
        """Verify film IDs are correctly extracted from URLs."""
        html_content = load_html_snapshot("cine_colombia___all_movies.html")

        movies = CineColombiaScraperAndHTMLParser.parse_movies_from_films_page(html_content)

        housemaid = next((m for m in movies if "Empleada" in m.title), None)
        assert housemaid is not None
        assert housemaid.film_id == "HO00000338"

    def test_parse_movies_extracts_url(self):
        """Verify movie URLs are correctly extracted."""
        html_content = load_html_snapshot("cine_colombia___all_movies.html")

        movies = CineColombiaScraperAndHTMLParser.parse_movies_from_films_page(html_content)

        housemaid = next((m for m in movies if "Empleada" in m.title), None)
        assert housemaid is not None
        assert "cinecolombia.com/films/the-housemaid/HO00000338" in housemaid.url

    def test_parse_movies_returns_empty_for_no_film_list(self):
        """Return empty list when no film list grid found."""
        html_content = "<html><body></body></html>"

        movies = CineColombiaScraperAndHTMLParser.parse_movies_from_films_page(html_content)

        assert movies == []


# =============================================================================
# Tests: Find Movies for Chain
# =============================================================================


@pytest.mark.django_db
class TestCineColombiaFindMoviesForChain:
    """Tests for the _find_movies_for_chain method."""

    def test_returns_movies_from_films_page(
        self, mock_tmdb_service_for_cine_colombia, mock_storage_service_for_cine_colombia
    ):
        """Test _find_movies_for_chain fetches movies from the films page."""
        scraper = MagicMock(spec=CineColombiaScraperAndHTMLParser)
        scraper.download_films_page_html.return_value = "<html></html>"
        scraper.parse_movies_from_films_page.return_value = [
            CineColombiaMovie(film_id="HO00000338", title="La Empleada", url="https://cinecolombia.com/films/the-housemaid/HO00000338/"),
            CineColombiaMovie(film_id="HO00000350", title="Avatar", url="https://cinecolombia.com/films/avatar-fire-and-ash/HO00000350/"),
        ]
        scraper.generate_movie_source_url.side_effect = lambda fid: f"https://www.cinecolombia.com/films/{fid}"

        saver = CineColombiaShowtimeSaver(scraper, mock_tmdb_service_for_cine_colombia, mock_storage_service_for_cine_colombia)

        movies = saver._find_movies_for_chain()

        assert len(movies) == 2
        scraper.download_films_page_html.assert_called_once_with("https://www.cinecolombia.com/films/")

    def test_creates_operational_issue_on_network_error(
        self, mock_tmdb_service_for_cine_colombia, mock_storage_service_for_cine_colombia
    ):
        """Test _find_movies_for_chain handles network errors gracefully."""
        scraper = MagicMock(spec=CineColombiaScraperAndHTMLParser)
        scraper.download_films_page_html.side_effect = Exception("Network error")

        saver = CineColombiaShowtimeSaver(scraper, mock_tmdb_service_for_cine_colombia, mock_storage_service_for_cine_colombia)
        initial_count = OperationalIssue.objects.count()

        movies = saver._find_movies_for_chain()

        assert movies == []
        assert OperationalIssue.objects.count() == initial_count + 1
        issue = OperationalIssue.objects.latest("created_at")
        assert issue.name == "Cine Colombia Films Page Download Failed"

    def test_creates_operational_issue_when_no_movies_found(
        self, mock_tmdb_service_for_cine_colombia, mock_storage_service_for_cine_colombia
    ):
        """Test _find_movies_for_chain logs issue when no movies found."""
        scraper = MagicMock(spec=CineColombiaScraperAndHTMLParser)
        scraper.download_films_page_html.return_value = "<html></html>"
        scraper.parse_movies_from_films_page.return_value = []

        saver = CineColombiaShowtimeSaver(scraper, mock_tmdb_service_for_cine_colombia, mock_storage_service_for_cine_colombia)
        initial_count = OperationalIssue.objects.count()

        movies = saver._find_movies_for_chain()

        assert movies == []
        assert OperationalIssue.objects.count() == initial_count + 1
        issue = OperationalIssue.objects.latest("created_at")
        assert issue.name == "Cine Colombia No Movies on Films Page"

    def test_caches_movies_in_films_page_cache(
        self, mock_tmdb_service_for_cine_colombia, mock_storage_service_for_cine_colombia
    ):
        """Test _find_movies_for_chain populates the films page cache."""
        scraper = MagicMock(spec=CineColombiaScraperAndHTMLParser)
        scraper.download_films_page_html.return_value = "<html></html>"
        scraper.parse_movies_from_films_page.return_value = [
            CineColombiaMovie(film_id="HO00000338", title="La Empleada", url="https://cinecolombia.com/films/the-housemaid/HO00000338/"),
        ]
        scraper.generate_movie_source_url.return_value = "https://www.cinecolombia.com/films/HO00000338"

        saver = CineColombiaShowtimeSaver(scraper, mock_tmdb_service_for_cine_colombia, mock_storage_service_for_cine_colombia)

        saver._find_movies_for_chain()

        assert "HO00000338" in saver._films_page_cache
        cached_movie = saver._films_page_cache["HO00000338"]
        assert cached_movie.title == "La Empleada"


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
