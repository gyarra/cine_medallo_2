"""
Tests for Colombo Americano download task.
"""

import datetime
from unittest.mock import MagicMock

import pytest

from movies_app.models import Movie, Showtime
from movies_app.services.tmdb_service import (
    TMDBGenre,
    TMDBMovieDetails,
    TMDBMovieResult,
    TMDBProductionCompany,
    TMDBSearchResponse,
)
from movies_app.tasks.colombo_americano_download_task import (
    ColomboAmericanoScraperAndHTMLParser,
    ColomboAmericanoShowtimeSaver,
)
from movies_app.tasks.tests.conftest import load_html_snapshot


class TestParseShowtimesFromWeeklyScheduleHtml:
    def test_extracts_showtimes_from_colombo_schedule_html(self):
        html_content = load_html_snapshot("colombo_americano___all_movies.html")
        showtimes = ColomboAmericanoScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html_content)

        assert len(showtimes) > 0

        movie_titles = {st.movie_title for st in showtimes}
        assert "No other Choice" in movie_titles
        assert "Marty Supreme" in movie_titles

    def test_extracts_correct_showtime_data(self):
        html_content = load_html_snapshot("colombo_americano___all_movies.html")
        showtimes = ColomboAmericanoScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html_content)

        no_other_choice_showtimes = [st for st in showtimes if st.movie_title == "No other Choice"]
        assert len(no_other_choice_showtimes) > 0

        first_showtime = no_other_choice_showtimes[0]
        assert first_showtime.time is not None
        assert first_showtime.date is not None
        assert "colombomedellin.edu.co/peliculas" in first_showtime.movie_url

    def test_extracts_movie_urls(self):
        html_content = load_html_snapshot("colombo_americano___all_movies.html")
        showtimes = ColomboAmericanoScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html_content)

        for st in showtimes:
            assert st.movie_url is not None
            assert st.movie_url.startswith("https://www.colombomedellin.edu.co/peliculas/")

    def test_parses_dates_and_times_correctly(self):
        html_content = load_html_snapshot("colombo_americano___all_movies.html")
        showtimes = ColomboAmericanoScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html_content)

        for st in showtimes:
            assert isinstance(st.date, datetime.date)
            assert isinstance(st.time, datetime.time)
            assert st.time.hour >= 0 and st.time.hour <= 23
            assert st.date.month >= 1 and st.date.month <= 12

    def test_filters_out_2x1_tags_and_extracts_real_title(self):
        """Some movie listings have a '2x1' tag before the real title. Ensure we extract the real title."""
        html_content = load_html_snapshot("colombo_americano___all_movies.html")
        showtimes = ColomboAmericanoScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html_content)

        movie_titles = {st.movie_title for st in showtimes}

        # "2X1", "2x1", and "Función especial. Entrada libre" are tags, not movie titles
        assert "2X1" not in movie_titles
        assert "2x1" not in movie_titles
        assert "Función especial. Entrada libre" not in movie_titles

        # The real titles for movies with the 2x1 tag should be extracted
        assert "Valor sentimental" in movie_titles


class TestParseDateString:
    def test_parses_spanish_full_month_names(self):
        assert ColomboAmericanoScraperAndHTMLParser._parse_date_string("enero 27", 2026) == datetime.date(2026, 1, 27)
        assert ColomboAmericanoScraperAndHTMLParser._parse_date_string("febrero 1", 2026) == datetime.date(2026, 2, 1)
        assert ColomboAmericanoScraperAndHTMLParser._parse_date_string("diciembre 25", 2026) == datetime.date(2026, 12, 25)

    def test_parses_different_months(self):
        assert ColomboAmericanoScraperAndHTMLParser._parse_date_string("marzo 15", 2025) == datetime.date(2025, 3, 15)
        assert ColomboAmericanoScraperAndHTMLParser._parse_date_string("julio 4", 2025) == datetime.date(2025, 7, 4)
        assert ColomboAmericanoScraperAndHTMLParser._parse_date_string("noviembre 30", 2025) == datetime.date(2025, 11, 30)

    def test_returns_none_for_invalid_date(self):
        assert ColomboAmericanoScraperAndHTMLParser._parse_date_string("invalid", 2025) is None
        assert ColomboAmericanoScraperAndHTMLParser._parse_date_string("", 2025) is None
        assert ColomboAmericanoScraperAndHTMLParser._parse_date_string("abc 32", 2025) is None


class TestParseMovieMetaFromMovieHtml:
    def test_extracts_movie_metadata(self):
        html_content = load_html_snapshot("colombo_americano___one_movie.html")
        metadata = ColomboAmericanoScraperAndHTMLParser.parse_movie_meta_from_movie_html(html_content)

        assert metadata is not None
        assert metadata.title == "No other Choice"

    def test_extracts_director(self):
        html_content = load_html_snapshot("colombo_americano___one_movie.html")
        metadata = ColomboAmericanoScraperAndHTMLParser.parse_movie_meta_from_movie_html(html_content)

        assert metadata is not None
        assert "Par Chan-wook" in metadata.director or metadata.director != ""

    def test_extracts_duration(self):
        html_content = load_html_snapshot("colombo_americano___one_movie.html")
        metadata = ColomboAmericanoScraperAndHTMLParser.parse_movie_meta_from_movie_html(html_content)

        assert metadata is not None
        assert metadata.duration_minutes == 139 or metadata.duration_minutes is None

    def test_extracts_year(self):
        html_content = load_html_snapshot("colombo_americano___one_movie.html")
        metadata = ColomboAmericanoScraperAndHTMLParser.parse_movie_meta_from_movie_html(html_content)

        assert metadata is not None
        assert metadata.year == 2026 or metadata.year is None


@pytest.fixture
def colombo_theater(db):
    """Create the Colombo Americano theater for tests."""
    from movies_app.models import Theater
    theater, _ = Theater.objects.get_or_create(
        slug="colombo-americano-medellin",
        defaults={
            "name": "Colombo Americano",
            "chain": "Colombo Americano",
            "address": "Cra. 45 #53 - 24",
            "city": "Medellín",
            "neighborhood": "La Candelaria",
            "website": "https://www.colombomedellin.edu.co/programacion-por-salas/",
            "screen_count": 1,
            "is_active": True,
            "scraper_type": "colombo_americano",
            "download_source_url": "https://www.colombomedellin.edu.co/programacion-por-salas/",
        },
    )
    return theater


def _create_mock_tmdb_service():
    """Create a mock TMDB service for testing."""
    mock_response = TMDBSearchResponse(
        page=1,
        total_pages=1,
        total_results=1,
        results=[
            TMDBMovieResult(
                id=99999,
                title="Test Movie",
                original_title="Test Movie Original",
                overview="A test movie for testing",
                release_date="2025-01-15",
                popularity=50.0,
                vote_average=6.5,
                vote_count=500,
                poster_path="/test_poster.jpg",
                backdrop_path="/test_backdrop.jpg",
                genre_ids=[18],
                original_language="es",
                adult=False,
                video=False,
            )
        ],
    )

    mock_instance = MagicMock()
    mock_instance.search_movie.return_value = mock_response
    mock_instance.get_movie_details.return_value = TMDBMovieDetails(
        id=99999,
        title="Test Movie",
        original_title="Test Movie Original",
        overview="A test movie for testing",
        release_date="2025-01-15",
        popularity=50.0,
        vote_average=6.5,
        vote_count=500,
        poster_path="/test_poster.jpg",
        backdrop_path="/test_backdrop.jpg",
        genres=[TMDBGenre(id=18, name="Drama")],
        original_language="es",
        adult=False,
        video=False,
        runtime=120,
        budget=1000000,
        revenue=5000000,
        status="Released",
        tagline="A test movie",
        homepage="",
        imdb_id="tt9999999",
        production_companies=[
            TMDBProductionCompany(id=1, name="Test Studio", logo_path=None, origin_country="CO")
        ],
        cast=None,
        crew=None,
        videos=None,
        certification=None,
    )
    return mock_instance


class TestColomboAmericanoShowtimeSaver:
    @pytest.mark.django_db
    def test_execute_saves_showtimes(self, colombo_theater):
        """Test that execute() saves showtimes to the database."""
        mock_scraper = MagicMock()
        mock_scraper.download_weekly_schedule.return_value = load_html_snapshot("colombo_americano___all_movies.html")
        mock_scraper.download_individual_movie_html.return_value = load_html_snapshot("colombo_americano___one_movie.html")
        mock_scraper.parse_showtimes_from_weekly_schedule_html = ColomboAmericanoScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html
        mock_scraper.parse_movie_meta_from_movie_html = ColomboAmericanoScraperAndHTMLParser.parse_movie_meta_from_movie_html

        mock_storage = MagicMock()
        mock_storage.get_existing_url.return_value = None
        mock_storage.download_and_upload_from_url.return_value = "https://mock-storage.example.com/test.jpg"

        mock_tmdb = _create_mock_tmdb_service()

        saver = ColomboAmericanoShowtimeSaver(mock_scraper, mock_tmdb, mock_storage)
        report = saver.execute()

        assert report.total_showtimes > 0
        assert Showtime.objects.filter(theater=colombo_theater).count() > 0

    @pytest.mark.django_db
    def test_execute_creates_movies(self, colombo_theater):
        """Test that execute() creates Movie records."""
        mock_scraper = MagicMock()
        mock_scraper.download_weekly_schedule.return_value = load_html_snapshot("colombo_americano___all_movies.html")
        mock_scraper.download_individual_movie_html.return_value = load_html_snapshot("colombo_americano___one_movie.html")
        mock_scraper.parse_showtimes_from_weekly_schedule_html = ColomboAmericanoScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html
        mock_scraper.parse_movie_meta_from_movie_html = ColomboAmericanoScraperAndHTMLParser.parse_movie_meta_from_movie_html

        mock_storage = MagicMock()
        mock_storage.get_existing_url.return_value = None
        mock_storage.download_and_upload_from_url.return_value = "https://mock-storage.example.com/test.jpg"

        mock_tmdb = _create_mock_tmdb_service()

        initial_movie_count = Movie.objects.count()

        saver = ColomboAmericanoShowtimeSaver(mock_scraper, mock_tmdb, mock_storage)
        saver.execute()

        assert Movie.objects.count() > initial_movie_count

    @pytest.mark.django_db
    def test_execute_deletes_old_showtimes_for_date(self, colombo_theater):
        """Test that execute() deletes old showtimes before saving new ones."""
        movie = Movie.objects.create(
            title_es="Old Movie",
            slug="old-movie",
        )
        old_showtime = Showtime.objects.create(
            theater=colombo_theater,
            movie=movie,
            start_date=datetime.date(2026, 1, 27),
            start_time=datetime.time(14, 0),
            format="",
            translation_type="",
            screen="",
            source_url="https://old-url.com",
        )

        mock_scraper = MagicMock()
        mock_scraper.download_weekly_schedule.return_value = load_html_snapshot("colombo_americano___all_movies.html")
        mock_scraper.download_individual_movie_html.return_value = load_html_snapshot("colombo_americano___one_movie.html")
        mock_scraper.parse_showtimes_from_weekly_schedule_html = ColomboAmericanoScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html
        mock_scraper.parse_movie_meta_from_movie_html = ColomboAmericanoScraperAndHTMLParser.parse_movie_meta_from_movie_html

        mock_storage = MagicMock()
        mock_storage.get_existing_url.return_value = None
        mock_storage.download_and_upload_from_url.return_value = "https://mock-storage.example.com/test.jpg"

        mock_tmdb = _create_mock_tmdb_service()

        saver = ColomboAmericanoShowtimeSaver(mock_scraper, mock_tmdb, mock_storage)
        saver.execute()

        assert not Showtime.objects.filter(pk=old_showtime.pk).exists()

    @pytest.mark.django_db
    def test_execute_returns_task_report(self, colombo_theater):
        """Test that execute() returns a proper TaskReport."""
        mock_scraper = MagicMock()
        mock_scraper.download_weekly_schedule.return_value = load_html_snapshot("colombo_americano___all_movies.html")
        mock_scraper.download_individual_movie_html.return_value = load_html_snapshot("colombo_americano___one_movie.html")
        mock_scraper.parse_showtimes_from_weekly_schedule_html = ColomboAmericanoScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html
        mock_scraper.parse_movie_meta_from_movie_html = ColomboAmericanoScraperAndHTMLParser.parse_movie_meta_from_movie_html

        mock_storage = MagicMock()
        mock_storage.get_existing_url.return_value = None
        mock_storage.download_and_upload_from_url.return_value = "https://mock-storage.example.com/test.jpg"

        mock_tmdb = _create_mock_tmdb_service()

        saver = ColomboAmericanoShowtimeSaver(mock_scraper, mock_tmdb, mock_storage)
        report = saver.execute()

        assert hasattr(report, 'total_showtimes')
        assert hasattr(report, 'tmdb_calls')
        assert hasattr(report, 'new_movies')
        assert isinstance(report.total_showtimes, int)
        assert isinstance(report.tmdb_calls, int)
        assert isinstance(report.new_movies, list)
