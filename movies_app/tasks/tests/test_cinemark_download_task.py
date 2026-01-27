import datetime
import os
from unittest.mock import MagicMock

import pytest

from movies_app.models import Movie, MovieSourceUrl, OperationalIssue, Showtime, Theater
from movies_app.services.tmdb_service import (
    TMDBGenre,
    TMDBMovieDetails,
    TMDBMovieResult,
    TMDBProductionCompany,
    TMDBSearchResponse,
    TMDBService,
)
from movies_app.tasks.cinemark_download_task import (
    CinemarkMovieWithShowtimes,
    CinemarkScraperAndHTMLParser,
    CinemarkShowtimeBlock,
    CinemarkShowtimeSaver,
)


def load_html_snapshot(filename: str) -> str:
    html_snapshot_path = os.path.join(
        os.path.dirname(__file__),
        "html_snapshot",
        filename,
    )
    with open(html_snapshot_path, encoding="utf-8") as f:
        return f.read()


# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def cinemark_theater(db):
    """Create a Cinemark theater for tests."""
    theater, _ = Theater.objects.get_or_create(
        slug="cinemark-arkadia-medellin",
        defaults={
            "name": "Cinemark Arkadia",
            "chain": "Cinemark",
            "address": "C.C. Arkadia",
            "city": "Medellín",
            "neighborhood": "La Moto",
            "website": "https://www.cinemark.com.co/ciudad/medellin/arkadia",
            "screen_count": 9,
            "is_active": True,
            "scraper_type": "cinemark",
            "download_source_url": "https://www.cinemark.com.co/ciudad/medellin/arkadia",
        },
    )
    return theater


@pytest.fixture
def cinemark_theater_without_url(db):
    """Create a Cinemark theater without download_source_url."""
    theater, _ = Theater.objects.get_or_create(
        slug="cinemark-no-url",
        defaults={
            "name": "Cinemark Without URL",
            "chain": "Cinemark",
            "address": "Test Address",
            "city": "Test City",
            "is_active": True,
            "scraper_type": "cinemark",
            "download_source_url": "",
        },
    )
    return theater


@pytest.fixture
def mock_tmdb_service_for_cinemark():
    """Mock TMDB service for Cinemark tests."""
    mock_response = TMDBSearchResponse(
        page=1,
        total_pages=1,
        total_results=1,
        results=[
            TMDBMovieResult(
                id=123456,
                title="Sin Piedad",
                original_title="Mercy",
                overview="A detective story",
                release_date="2026-01-22",
                popularity=100.0,
                vote_average=7.5,
                vote_count=1000,
                poster_path="/sin_piedad_poster.jpg",
                backdrop_path="/sin_piedad_backdrop.jpg",
                genre_ids=[28, 53],
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
        title="Sin Piedad",
        original_title="Mercy",
        overview="A detective story",
        release_date="2026-01-22",
        popularity=100.0,
        vote_average=7.5,
        vote_count=1000,
        poster_path="/sin_piedad_poster.jpg",
        backdrop_path="/sin_piedad_backdrop.jpg",
        genres=[TMDBGenre(id=28, name="Action"), TMDBGenre(id=53, name="Thriller")],
        original_language="en",
        adult=False,
        video=False,
        runtime=100,
        budget=50000000,
        revenue=100000000,
        status="Released",
        tagline="No mercy",
        homepage="",
        imdb_id="tt1234567",
        production_companies=[
            TMDBProductionCompany(id=1, name="Test Studio", logo_path=None, origin_country="US")
        ],
        cast=None,
        crew=None,
        videos=None,
        certification=None,
    )
    return mock_instance


@pytest.fixture
def mock_storage_service_for_cinemark():
    """Mock storage service for Cinemark tests."""
    mock_service = MagicMock()
    mock_service.get_existing_url.return_value = None
    mock_service.upload_image_from_url.return_value = "https://mock-storage.example.com/poster.jpg"
    mock_service.download_and_upload_from_url.return_value = "https://mock-storage.example.com/poster.jpg"
    return mock_service


# =============================================================================
# CinemarkScraperAndHTMLParser Tests - Parse Movies from Cartelera
# =============================================================================


class TestParseMoviesFromCarteleraHtml:
    def test_extracts_movies_from_cartelera_html(self):
        html_content = load_html_snapshot("cinemark___movies_for_one_theater.html")
        test_date = datetime.date(2026, 1, 26)

        movies = CinemarkScraperAndHTMLParser._parse_movies_from_cartelera_html(html_content, test_date)

        assert len(movies) > 0

    def test_extracts_correct_movie_titles(self):
        html_content = load_html_snapshot("cinemark___movies_for_one_theater.html")
        test_date = datetime.date(2026, 1, 26)

        movies = CinemarkScraperAndHTMLParser._parse_movies_from_cartelera_html(html_content, test_date)

        titles = {m.title for m in movies}
        # These movies appear in the HTML snapshot
        assert "La Empleada" in titles
        assert "Avatar Fuego y Cenizas" in titles

    def test_extracts_movie_urls_with_cartelera_path(self):
        html_content = load_html_snapshot("cinemark___movies_for_one_theater.html")
        test_date = datetime.date(2026, 1, 26)

        movies = CinemarkScraperAndHTMLParser._parse_movies_from_cartelera_html(html_content, test_date)

        # All URLs should contain /cartelera/
        for movie in movies:
            assert "/cartelera/" in movie.url

    def test_extracts_showtimes_for_each_movie(self):
        html_content = load_html_snapshot("cinemark___movies_for_one_theater.html")
        test_date = datetime.date(2026, 1, 26)

        movies = CinemarkScraperAndHTMLParser._parse_movies_from_cartelera_html(html_content, test_date)

        # Each movie should have showtime blocks
        for movie in movies:
            assert len(movie.showtime_blocks) > 0


class TestParseShowtimeBlocks:
    def test_extracts_showtime_times(self):
        html_content = load_html_snapshot("cinemark___movies_for_one_theater.html")
        test_date = datetime.date(2026, 1, 26)

        movies = CinemarkScraperAndHTMLParser._parse_movies_from_cartelera_html(html_content, test_date)

        # Find a movie with showtimes
        movie_with_showtimes = next((m for m in movies if m.showtime_blocks), None)
        assert movie_with_showtimes is not None

        # Get all times across all blocks
        all_times = []
        for block in movie_with_showtimes.showtime_blocks:
            all_times.extend(block.times)
        assert len(all_times) > 0

    def test_extracts_format_and_translation_type(self):
        html_content = load_html_snapshot("cinemark___movies_for_one_theater.html")
        test_date = datetime.date(2026, 1, 26)

        movies = CinemarkScraperAndHTMLParser._parse_movies_from_cartelera_html(html_content, test_date)

        # Find a movie with showtimes
        movie_with_showtimes = next((m for m in movies if m.showtime_blocks), None)
        assert movie_with_showtimes is not None

        formats = {block.format for block in movie_with_showtimes.showtime_blocks}
        translation_types = {block.translation_type for block in movie_with_showtimes.showtime_blocks}

        assert "2D" in formats or "3D" in formats
        assert "Doblada" in translation_types or "Subtitulada" in translation_types or "Subtitulado" in translation_types


class TestParseDateString:
    def test_parses_full_date(self):
        date = CinemarkScraperAndHTMLParser._parse_date_string("27 ene. 2026")
        assert date is not None
        assert date.year == 2026
        assert date.month == 1
        assert date.day == 27

    def test_parses_date_without_period(self):
        date = CinemarkScraperAndHTMLParser._parse_date_string("27 ene 2026")
        assert date is not None
        assert date.year == 2026
        assert date.month == 1
        assert date.day == 27

    def test_parses_all_spanish_months(self):
        months = [
            ("15 ene 2026", 1),
            ("15 feb 2026", 2),
            ("15 mar 2026", 3),
            ("15 abr 2026", 4),
            ("15 may 2026", 5),
            ("15 jun 2026", 6),
            ("15 jul 2026", 7),
            ("15 ago 2026", 8),
            ("15 sep 2026", 9),
            ("15 oct 2026", 10),
            ("15 nov 2026", 11),
            ("15 dic 2026", 12),
        ]
        for date_str, expected_month in months:
            date = CinemarkScraperAndHTMLParser._parse_date_string(date_str)
            assert date is not None, f"Failed to parse {date_str}"
            assert date.month == expected_month

    def test_returns_none_for_invalid_format(self):
        date = CinemarkScraperAndHTMLParser._parse_date_string("invalid date")
        assert date is None


class TestExtractSlugFromUrl:
    def test_extracts_slug_from_cartelera_url(self):
        slug = CinemarkScraperAndHTMLParser.extract_slug_from_url(
            "https://www.cinemark.com.co/cartelera/medellin/sin-piedad"
        )
        assert slug == "sin-piedad"

    def test_extracts_slug_with_dashes(self):
        slug = CinemarkScraperAndHTMLParser.extract_slug_from_url(
            "https://www.cinemark.com.co/cartelera/medellin/twenty-one-pilots-more"
        )
        assert slug == "twenty-one-pilots-more"

    def test_extracts_slug_from_simple_url(self):
        slug = CinemarkScraperAndHTMLParser.extract_slug_from_url(
            "https://www.cinemark.com.co/sin-piedad"
        )
        assert slug == "sin-piedad"


class TestGenerateMovieSourceUrl:
    def test_converts_cartelera_url_to_canonical_format(self):
        url = CinemarkScraperAndHTMLParser.generate_movie_source_url(
            "https://www.cinemark.com.co/cartelera/medellin/sin-piedad"
        )
        assert url == "https://www.cinemark.com.co/sin-piedad"

    def test_handles_different_cities(self):
        url = CinemarkScraperAndHTMLParser.generate_movie_source_url(
            "https://www.cinemark.com.co/cartelera/bogota/la-empleada"
        )
        assert url == "https://www.cinemark.com.co/la-empleada"

    def test_returns_original_if_no_slug_extracted(self):
        url = CinemarkScraperAndHTMLParser.generate_movie_source_url(
            "https://www.cinemark.com.co/"
        )
        assert url == "https://www.cinemark.com.co/"


# =============================================================================
# Parser Edge Case Tests
# =============================================================================


class TestParseMoviesEdgeCases:
    def test_returns_empty_list_for_empty_html(self):
        movies = CinemarkScraperAndHTMLParser._parse_movies_from_cartelera_html(
            "", datetime.date(2026, 1, 27)
        )
        assert movies == []

    def test_returns_empty_list_for_no_movie_sections(self):
        html = "<html><body><div class='list-movies'><div class='d-block'></div></div></body></html>"
        movies = CinemarkScraperAndHTMLParser._parse_movies_from_cartelera_html(
            html, datetime.date(2026, 1, 27)
        )
        assert movies == []


# =============================================================================
# CinemarkShowtimeSaver Tests
# =============================================================================


@pytest.mark.django_db
class TestCinemarkShowtimeSaverFindMovies:
    def test_returns_empty_list_when_no_url(
        self, cinemark_theater_without_url, mock_tmdb_service_for_cinemark, mock_storage_service_for_cinemark
    ):
        scraper = CinemarkScraperAndHTMLParser()
        saver = CinemarkShowtimeSaver(scraper, mock_tmdb_service_for_cinemark, mock_storage_service_for_cinemark)

        movies = saver._find_movies(cinemark_theater_without_url)

        assert movies == []
        issue = OperationalIssue.objects.filter(name="Cinemark Missing Source URL").latest("created_at")
        assert "Cinemark Without URL" in issue.error_message

    def test_creates_issue_when_scrape_fails(
        self, cinemark_theater, mock_tmdb_service_for_cinemark, mock_storage_service_for_cinemark
    ):
        scraper = MagicMock(spec=CinemarkScraperAndHTMLParser)
        scraper.scrape_theater_movies_and_showtimes.side_effect = Exception("Scrape error")

        saver = CinemarkShowtimeSaver(scraper, mock_tmdb_service_for_cinemark, mock_storage_service_for_cinemark)
        initial_count = OperationalIssue.objects.count()

        movies = saver._find_movies(cinemark_theater)

        assert movies == []
        assert OperationalIssue.objects.count() == initial_count + 1
        issue = OperationalIssue.objects.latest("created_at")
        assert issue.name == "Cinemark Scrape Failed"

    def test_creates_issue_when_no_movies_found(
        self, cinemark_theater, mock_tmdb_service_for_cinemark, mock_storage_service_for_cinemark
    ):
        scraper = MagicMock(spec=CinemarkScraperAndHTMLParser)
        scraper.scrape_theater_movies_and_showtimes.return_value = []

        saver = CinemarkShowtimeSaver(scraper, mock_tmdb_service_for_cinemark, mock_storage_service_for_cinemark)
        initial_count = OperationalIssue.objects.count()

        movies = saver._find_movies(cinemark_theater)

        assert movies == []
        assert OperationalIssue.objects.count() == initial_count + 1
        issue = OperationalIssue.objects.latest("created_at")
        assert issue.name == "Cinemark No Movies Found"


# =============================================================================
# Integration Tests - Full Task Flow with Mocked Dependencies
# =============================================================================


def _create_tmdb_service_with_unique_results():
    """Create a mock TMDB service that returns unique movies for each search."""
    call_counter = [0]

    def search_movie_side_effect(*args, **kwargs):
        call_counter[0] += 1
        return TMDBSearchResponse(
            page=1,
            total_pages=1,
            total_results=1,
            results=[
                TMDBMovieResult(
                    id=100000 + call_counter[0],
                    title=f"Movie {call_counter[0]}",
                    original_title=f"Original Movie {call_counter[0]}",
                    overview="A test movie",
                    release_date="2026-01-22",
                    popularity=100.0,
                    vote_average=7.5,
                    vote_count=1000,
                    poster_path=f"/poster_{call_counter[0]}.jpg",
                    backdrop_path=f"/backdrop_{call_counter[0]}.jpg",
                    genre_ids=[28],
                    original_language="en",
                    adult=False,
                    video=False,
                )
            ],
        )

    def get_movie_details_side_effect(movie_id, include_credits=True):
        return TMDBMovieDetails(
            id=movie_id,
            title=f"Movie {movie_id - 100000}",
            original_title=f"Original Movie {movie_id - 100000}",
            overview="A test movie",
            tagline="",
            status="Released",
            release_date="2026-01-22",
            popularity=100.0,
            vote_average=7.5,
            vote_count=1000,
            budget=0,
            revenue=0,
            runtime=120,
            original_language="en",
            poster_path=f"/poster_{movie_id - 100000}.jpg",
            backdrop_path=f"/backdrop_{movie_id - 100000}.jpg",
            imdb_id=None,
            homepage="",
            genres=[TMDBGenre(id=28, name="Action")],
            production_companies=[TMDBProductionCompany(id=1, name="Test Studio", logo_path=None, origin_country="US")],
            adult=False,
            video=False,
            cast=None,
            crew=None,
            videos=None,
            certification=None,
        )

    mock_instance = MagicMock(spec=TMDBService)
    mock_instance.search_movie.side_effect = search_movie_side_effect
    mock_instance.get_movie_details.side_effect = get_movie_details_side_effect
    return mock_instance


@pytest.mark.django_db
class TestCinemarkShowtimeSaverIntegration:
    def test_full_execute_flow_with_single_movie(
        self, cinemark_theater, mock_storage_service_for_cinemark
    ):
        """Integration test: Full execute() flow with a single movie."""
        scraper = MagicMock(spec=CinemarkScraperAndHTMLParser)
        scraper.scrape_theater_movies_and_showtimes.return_value = [
            CinemarkMovieWithShowtimes(
                title="Sin Piedad",
                url="https://www.cinemark.com.co/cartelera/medellin/sin-piedad",
                date=datetime.date(2026, 1, 27),
                showtime_blocks=[
                    CinemarkShowtimeBlock(
                        format="2D",
                        translation_type="Doblada",
                        seat_type="General",
                        times=[datetime.time(19, 0), datetime.time(21, 45)],
                    ),
                ],
            ),
        ]
        scraper.generate_movie_source_url.side_effect = lambda url: url

        tmdb_service = _create_tmdb_service_with_unique_results()
        saver = CinemarkShowtimeSaver(scraper, tmdb_service, mock_storage_service_for_cinemark)

        report = saver.execute()

        assert report.total_showtimes > 0
        assert Showtime.objects.filter(theater=cinemark_theater).exists()
        assert Movie.objects.exists()

    def test_execute_for_single_theater_with_single_movie(
        self, cinemark_theater, mock_storage_service_for_cinemark
    ):
        """Test execute_for_theater() processes a single theater with a single movie."""
        scraper = MagicMock(spec=CinemarkScraperAndHTMLParser)
        scraper.scrape_theater_movies_and_showtimes.return_value = [
            CinemarkMovieWithShowtimes(
                title="Sin Piedad",
                url="https://www.cinemark.com.co/cartelera/medellin/sin-piedad",
                date=datetime.date(2026, 1, 27),
                showtime_blocks=[
                    CinemarkShowtimeBlock(
                        format="2D",
                        translation_type="Doblada",
                        seat_type="General",
                        times=[datetime.time(19, 0), datetime.time(21, 45)],
                    ),
                ],
            ),
        ]
        scraper.generate_movie_source_url.side_effect = lambda url: url

        tmdb_service = _create_tmdb_service_with_unique_results()
        saver = CinemarkShowtimeSaver(scraper, tmdb_service, mock_storage_service_for_cinemark)

        showtimes_count = saver.execute_for_theater(cinemark_theater)

        assert showtimes_count > 0
        assert Showtime.objects.filter(theater=cinemark_theater).count() == showtimes_count

    def test_handles_theater_processing_error_gracefully(
        self, cinemark_theater, mock_tmdb_service_for_cinemark, mock_storage_service_for_cinemark
    ):
        """Test that errors during theater processing are caught and logged."""
        scraper = MagicMock(spec=CinemarkScraperAndHTMLParser)
        scraper.scrape_theater_movies_and_showtimes.side_effect = Exception("Network error")

        saver = CinemarkShowtimeSaver(scraper, mock_tmdb_service_for_cinemark, mock_storage_service_for_cinemark)
        initial_count = OperationalIssue.objects.count()

        report = saver.execute()

        assert report.total_showtimes == 0
        assert OperationalIssue.objects.count() > initial_count

    def test_creates_movie_source_url_link(
        self, cinemark_theater, mock_storage_service_for_cinemark
    ):
        """Test that MovieSourceUrl is created linking movie to scraper URL."""
        scraper = MagicMock(spec=CinemarkScraperAndHTMLParser)
        scraper.scrape_theater_movies_and_showtimes.return_value = [
            CinemarkMovieWithShowtimes(
                title="Sin Piedad",
                url="https://www.cinemark.com.co/cartelera/medellin/sin-piedad",
                date=datetime.date(2026, 1, 27),
                showtime_blocks=[
                    CinemarkShowtimeBlock(
                        format="2D",
                        translation_type="Doblada",
                        seat_type="General",
                        times=[datetime.time(19, 0)],
                    ),
                ],
            ),
        ]
        scraper.generate_movie_source_url.side_effect = lambda url: url

        tmdb_service = _create_tmdb_service_with_unique_results()
        saver = CinemarkShowtimeSaver(scraper, tmdb_service, mock_storage_service_for_cinemark)
        saver.execute()

        assert MovieSourceUrl.objects.filter(scraper_type=MovieSourceUrl.ScraperType.CINEMARK).exists()

    def test_deletes_existing_showtimes_before_saving_new(
        self, cinemark_theater, mock_storage_service_for_cinemark
    ):
        """Test that existing showtimes are deleted before saving new ones."""
        scraper = MagicMock(spec=CinemarkScraperAndHTMLParser)
        scraper.scrape_theater_movies_and_showtimes.return_value = [
            CinemarkMovieWithShowtimes(
                title="Sin Piedad",
                url="https://www.cinemark.com.co/cartelera/medellin/sin-piedad",
                date=datetime.date(2026, 1, 27),
                showtime_blocks=[
                    CinemarkShowtimeBlock(
                        format="2D",
                        translation_type="Doblada",
                        seat_type="General",
                        times=[datetime.time(19, 0), datetime.time(21, 45)],
                    ),
                ],
            ),
        ]
        scraper.generate_movie_source_url.side_effect = lambda url: url

        tmdb_service = _create_tmdb_service_with_unique_results()
        saver = CinemarkShowtimeSaver(scraper, tmdb_service, mock_storage_service_for_cinemark)

        saver.execute()
        first_count = Showtime.objects.filter(theater=cinemark_theater).count()

        tmdb_service_2 = _create_tmdb_service_with_unique_results()
        saver2 = CinemarkShowtimeSaver(scraper, tmdb_service_2, mock_storage_service_for_cinemark)
        saver2.execute()
        second_count = Showtime.objects.filter(theater=cinemark_theater).count()

        assert first_count == second_count


@pytest.mark.django_db
class TestCinemarkShowtimeSaverMovieDeduplication:
    def test_does_not_lookup_movie_twice_across_theaters(
        self, mock_storage_service_for_cinemark, db
    ):
        """Test movie deduplication: same movie at multiple theaters only looked up once."""
        Theater.objects.create(
            slug="cinemark-theater-1",
            name="Cinemark Theater 1",
            chain="Cinemark",
            address="Address 1",
            city="City",
            is_active=True,
            scraper_type="cinemark",
            download_source_url="https://www.cinemark.com.co/ciudad/city/theater1",
        )
        Theater.objects.create(
            slug="cinemark-theater-2",
            name="Cinemark Theater 2",
            chain="Cinemark",
            address="Address 2",
            city="City",
            is_active=True,
            scraper_type="cinemark",
            download_source_url="https://www.cinemark.com.co/ciudad/city/theater2",
        )

        scraper = MagicMock(spec=CinemarkScraperAndHTMLParser)
        scraper.scrape_theater_movies_and_showtimes.return_value = [
            CinemarkMovieWithShowtimes(
                title="Same Movie",
                url="https://www.cinemark.com.co/cartelera/city/same-movie",
                date=datetime.date(2026, 1, 27),
                showtime_blocks=[
                    CinemarkShowtimeBlock(
                        format="2D",
                        translation_type="Doblada",
                        seat_type="General",
                        times=[datetime.time(19, 0)],
                    ),
                ],
            ),
        ]
        scraper.generate_movie_source_url.side_effect = lambda url: url

        mock_tmdb = _create_tmdb_service_with_unique_results()
        saver = CinemarkShowtimeSaver(scraper, mock_tmdb, mock_storage_service_for_cinemark)

        saver.execute()

        # Movie should only be looked up once despite being at two theaters
        assert mock_tmdb.search_movie.call_count == 1
