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
from movies_app.tasks.cineprox_download_task import (
    CineproxMovieCard,
    CineproxScraperAndHTMLParser,
    CineproxShowtimeSaver,
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
def cineprox_theater(db):
    """Create a Cineprox theater for tests."""
    theater, _ = Theater.objects.get_or_create(
        slug="parque-fabricato",
        defaults={
            "name": "Parque Fabricato",
            "chain": "Cineprox",
            "address": "Calle 30 # 50-280",
            "city": "Bello",
            "neighborhood": "",
            "website": "https://www.cineprox.com",
            "screen_count": 6,
            "is_active": True,
            "scraper_type": "cineprox",
            "download_source_url": "https://www.cineprox.com/cartelera/bello/parque-fabricato",
            "scraper_config": {"city_id": "30", "theater_id": "328"},
        },
    )
    return theater


@pytest.fixture
def cineprox_theater_without_config(db):
    """Create a Cineprox theater without scraper_config."""
    theater, _ = Theater.objects.get_or_create(
        slug="theater-no-config",
        defaults={
            "name": "Theater Without Config",
            "chain": "Cineprox",
            "address": "Test Address",
            "city": "Test City",
            "is_active": True,
            "scraper_type": "cineprox",
            "download_source_url": "https://www.cineprox.com/cartelera/test/test",
            "scraper_config": None,
        },
    )
    return theater


@pytest.fixture
def cineprox_theater_incomplete_config(db):
    """Create a Cineprox theater with incomplete scraper_config."""
    theater, _ = Theater.objects.get_or_create(
        slug="theater-incomplete-config",
        defaults={
            "name": "Theater Incomplete Config",
            "chain": "Cineprox",
            "address": "Test Address",
            "city": "Test City",
            "is_active": True,
            "scraper_type": "cineprox",
            "download_source_url": "https://www.cineprox.com/cartelera/test/test",
            "scraper_config": {"city_id": "30"},
        },
    )
    return theater


@pytest.fixture
def mock_tmdb_service_for_cineprox():
    """Mock TMDB service for Cineprox tests."""
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
def mock_storage_service_for_cineprox():
    """Mock storage service for Cineprox tests."""
    mock_service = MagicMock()
    mock_service.get_existing_url.return_value = None
    mock_service.upload_image_from_url.return_value = "https://mock-storage.example.com/poster.jpg"
    mock_service.download_and_upload_from_url.return_value = "https://mock-storage.example.com/poster.jpg"
    return mock_service


# =============================================================================
# CineproxScraperAndHTMLParser Tests - Parse Movies from Cartelera
# =============================================================================


class TestParseMoviesFromCarteleraHtml:
    def test_extracts_movies_from_cartelera_html(self):
        html_content = load_html_snapshot("cineprox___movies_for_one_theater.html")

        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)

        assert len(movies) > 0

        movie_ids = {m.movie_id for m in movies}
        assert "2003" in movie_ids
        assert "2005" in movie_ids
        assert "1940" in movie_ids
        assert "1892" in movie_ids

    def test_extracts_correct_movie_data(self):
        html_content = load_html_snapshot("cineprox___movies_for_one_theater.html")

        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)

        sin_piedad_movies = [m for m in movies if m.movie_id == "2005"]
        assert len(sin_piedad_movies) == 1

        sin_piedad = sin_piedad_movies[0]
        assert sin_piedad.title == "SIN PIEDAD"
        assert sin_piedad.category == "estrenos"
        assert sin_piedad.slug == "sin-piedad"
        assert "pantallascineprox.com/img/peliculas/2005.jpg" in sin_piedad.poster_url

    def test_extracts_movie_categories(self):
        html_content = load_html_snapshot("cineprox___movies_for_one_theater.html")

        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)

        categories = {m.category for m in movies}
        assert "preventa" in categories
        assert "estrenos" in categories
        assert "cartelera" in categories
        assert "pronto" in categories

    def test_filters_pronto_movies_correctly(self):
        html_content = load_html_snapshot("cineprox___movies_for_one_theater.html")

        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)

        pronto_movies = [m for m in movies if m.category == "pronto"]
        active_movies = [m for m in movies if m.category != "pronto"]

        assert len(pronto_movies) > 0
        assert len(active_movies) > 0

    def test_extracts_featured_movies_from_destacadas_section(self):
        html_content = load_html_snapshot("cineprox___movies_for_one_theater___with_destacadadas.html")

        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)

        assert len(movies) > 0

        featured_ids = {"2003", "2018", "1972", "1940"}
        movie_ids = {m.movie_id for m in movies}
        for featured_id in featured_ids:
            assert featured_id in movie_ids, f"Featured movie {featured_id} should be included"

    def test_extracts_featured_movie_data_correctly(self):
        html_content = load_html_snapshot("cineprox___movies_for_one_theater___with_destacadadas.html")

        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)

        goat_movies = [m for m in movies if m.movie_id == "2003"]
        assert len(goat_movies) == 1
        goat = goat_movies[0]
        assert goat.title == "GOAT: LA CABRA QUE CAMBIO EL JUEGO"
        assert goat.category == "preventa"
        assert "pantallascineprox.com/img/peliculas/2003.jpg" in goat.poster_url

    def test_featured_movies_are_not_duplicated_in_grid(self):
        html_content = load_html_snapshot("cineprox___movies_for_one_theater___with_destacadadas.html")

        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)

        movie_ids = [m.movie_id for m in movies]
        assert len(movie_ids) == len(set(movie_ids)), "No duplicate movie IDs should exist"
    def test_extracts_metadata_from_detail_page(self):
        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        metadata = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html(html_content)

        assert metadata is not None
        assert metadata.title == "SIN PIEDAD"
        assert metadata.original_title == "MERCY"
        assert "detective Chris Raven" in metadata.synopsis
        assert metadata.classification == "12 Años"
        assert metadata.duration_minutes == 100
        assert metadata.genre == "Acción"
        assert metadata.country == "ESTADOS UNIDOS"
        assert metadata.director == "Timur Bekmambetov"
        assert "Chris Pratt" in metadata.actors
        assert "Rebecca Ferguson" in metadata.actors

    def test_extracts_release_date(self):
        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        metadata = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html(html_content)

        assert metadata is not None
        assert metadata.release_date is not None
        assert metadata.release_date.year == 2026
        assert metadata.release_date.month == 1
        assert metadata.release_date.day == 22

    def test_extracts_poster_url(self):
        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        metadata = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html(html_content)

        assert metadata is not None
        assert "pantallascineprox.com/img/peliculas/2005.jpg" in metadata.poster_url


class TestParseShowtimesFromDetailHtml:
    def test_extracts_showtimes_for_theater(self):
        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Parque Fabricato",
        )

        assert len(showtimes) > 0

    def test_extracts_correct_showtime_data(self):
        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Parque Fabricato",
        )

        assert len(showtimes) >= 3

        times = {st.time for st in showtimes}
        assert datetime.time(16, 25) in times
        assert datetime.time(18, 40) in times
        assert datetime.time(21, 25) in times

    def test_extracts_format_and_language(self):
        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Parque Fabricato",
        )

        assert len(showtimes) > 0
        first_showtime = showtimes[0]
        assert first_showtime.format == "2D"
        assert first_showtime.translation_type == "Doblada"

    def test_extracts_room_type(self):
        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Parque Fabricato",
        )

        assert len(showtimes) > 0
        first_showtime = showtimes[0]
        assert first_showtime.room_type == "General"

    def test_extracts_price(self):
        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Parque Fabricato",
        )

        assert len(showtimes) > 0
        first_showtime = showtimes[0]
        assert first_showtime.price is not None
        assert "21.900" in first_showtime.price


class TestParseAvailableDatesFromDetailHtml:
    def test_extracts_available_dates(self):
        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        dates = CineproxScraperAndHTMLParser.parse_available_dates_from_detail_html(
            html_content,
            reference_year=2026,
        )

        assert len(dates) >= 5

        days = {d.day for d in dates}
        assert 24 in days
        assert 25 in days
        assert 26 in days
        assert 27 in days
        assert 28 in days


class TestIsTheaterAccordionExpanded:
    def test_detects_expanded_accordion(self):
        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        is_expanded = CineproxScraperAndHTMLParser.is_theater_accordion_expanded(
            html_content,
            "Parque Fabricato",
        )

        assert is_expanded is True

    def test_detects_collapsed_accordion(self):
        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        is_expanded = CineproxScraperAndHTMLParser.is_theater_accordion_expanded(
            html_content,
            "Puerta del Norte",
        )

        assert is_expanded is False


class TestTheaterNamesMatch:
    def test_matches_exact_name(self):
        assert CineproxScraperAndHTMLParser._theater_names_match(
            "Parque Fabricato - Bello",
            "Parque Fabricato",
        ) is True

    def test_matches_partial_name(self):
        assert CineproxScraperAndHTMLParser._theater_names_match(
            "Puerta del Norte - Bello",
            "Puerta del Norte",
        ) is True

    def test_no_match_different_theaters(self):
        assert CineproxScraperAndHTMLParser._theater_names_match(
            "Parque Fabricato - Bello",
            "Puerta del Norte",
        ) is False


class TestParseFormatAndLanguage:
    def test_parses_2d_dob(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("2D - DOB")
        assert format_str == "2D"
        assert language == "Doblada"

    def test_parses_3d_sub(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("3D - SUB")
        assert format_str == "3D"
        assert language == "Subtitulada"

    def test_parses_2d_sub(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("2D - SUB")
        assert format_str == "2D"
        assert language == "Subtitulada"

    def test_parses_3d_dob(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("3D - DOB")
        assert format_str == "3D"
        assert language == "Doblada"

    def test_parses_format_only(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("2D")
        assert format_str == "2D"
        assert language == ""

    def test_unknown_language_code_preserved(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("2D - ESP")
        assert format_str == "2D"
        assert language == "ESP"


class TestParseReleaseDate:
    def test_parses_spanish_month_format(self):
        date = CineproxScraperAndHTMLParser._parse_release_date("22/enero/2026")
        assert date is not None
        assert date.year == 2026
        assert date.month == 1
        assert date.day == 22

    def test_parses_numeric_format(self):
        date = CineproxScraperAndHTMLParser._parse_release_date("15/03/2026")
        assert date is not None
        assert date.year == 2026
        assert date.month == 3
        assert date.day == 15

    def test_returns_none_for_invalid_format(self):
        date = CineproxScraperAndHTMLParser._parse_release_date("invalid date")
        assert date is None


class TestGenerateUrls:
    def test_generate_movie_detail_url_with_params(self):
        url = CineproxScraperAndHTMLParser.generate_movie_detail_url(
            movie_id="2005",
            slug="sin-piedad",
            city_id="30",
            theater_id="328",
        )

        assert url == "https://www.cineprox.com/detalle-pelicula/2005-sin-piedad?idCiudad=30&idTeatro=328"

    def test_generate_movie_detail_url_without_params(self):
        url = CineproxScraperAndHTMLParser.generate_movie_detail_url(
            movie_id="2005",
            slug="sin-piedad",
            city_id=None,
            theater_id=None,
        )

        assert url == "https://www.cineprox.com/detalle-pelicula/2005-sin-piedad"

    def test_generate_movie_source_url(self):
        url = CineproxScraperAndHTMLParser.generate_movie_source_url(
            movie_id="2005",
            slug="sin-piedad",
        )

        assert url == "https://www.cineprox.com/detalle-pelicula/2005-sin-piedad"


@pytest.mark.django_db
class TestParseShowtimesOperationalIssues:
    def test_creates_operational_issue_for_unparseable_time(self):
        html_with_invalid_time = """
        <div class="accordion-item">
            <button class="accordion-button">Parque Fabricato - Bello</button>
            <div class="accordion-collapse show">
                <div class="tab-pane">
                    <h5 class="tipoSala"><b>General</b></h5>
                    <div class="col-sm-6">
                        <div class="movie-schedule-header">2D - DOB</div>
                        <div class="movie-schedule-card">
                            <div class="movie-schedule-time">INVALID_TIME</div>
                            <div class="movie-schedule-price">$21.900</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """
        initial_count = OperationalIssue.objects.count()

        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_with_invalid_time,
            datetime.date(2026, 1, 24),
            "Parque Fabricato",
        )

        assert len(showtimes) == 0
        assert OperationalIssue.objects.count() == initial_count + 1

        issue = OperationalIssue.objects.latest("created_at")
        assert issue.name == "Time Parse Failed"
        assert issue.task == "cineprox_download_task"
        assert "INVALID_TIME" in issue.error_message
        assert issue.context["theater"] == "Parque Fabricato"
        assert issue.context["date"] == "2026-01-24"
        assert issue.severity == OperationalIssue.Severity.WARNING


# =============================================================================
# Additional Parser Edge Case Tests
# =============================================================================


class TestParseMoviesFromCarteleraEdgeCases:
    def test_returns_empty_list_when_no_grid_div(self):
        html_content = "<html><body><div>No grid here</div></body></html>"
        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)
        assert movies == []

    def test_returns_empty_list_for_empty_html(self):
        html_content = ""
        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)
        assert movies == []

    def test_skips_cards_without_movie_card_prefix(self):
        html_content = """
        <div id="grid">
            <div data-testid="other-card-123">
                <p class="card-text">Should be skipped</p>
            </div>
            <div data-testid="movie-card-456">
                <p class="card-text">Valid Movie</p>
            </div>
        </div>
        """
        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)
        assert len(movies) == 1
        assert movies[0].title == "Valid Movie"
        assert movies[0].movie_id == "456"

    def test_skips_cards_without_title_element(self):
        html_content = """
        <div id="grid">
            <div data-testid="movie-card-123">
                <div>No title here</div>
            </div>
        </div>
        """
        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)
        assert movies == []


class TestExtractCategoryFromClasses:
    def test_extracts_preventa(self):
        assert CineproxScraperAndHTMLParser._extract_category_from_classes(["card", "preventa", "active"]) == "preventa"

    def test_extracts_estrenos(self):
        assert CineproxScraperAndHTMLParser._extract_category_from_classes(["estrenos"]) == "estrenos"

    def test_extracts_cartelera(self):
        assert CineproxScraperAndHTMLParser._extract_category_from_classes(["cartelera", "other"]) == "cartelera"

    def test_extracts_pronto(self):
        assert CineproxScraperAndHTMLParser._extract_category_from_classes(["pronto"]) == "pronto"

    def test_returns_empty_for_no_category(self):
        assert CineproxScraperAndHTMLParser._extract_category_from_classes(["card", "active"]) == ""

    def test_returns_empty_for_empty_list(self):
        assert CineproxScraperAndHTMLParser._extract_category_from_classes([]) == ""


class TestParseMovieMetadataEdgeCases:
    def test_returns_none_when_no_pelicula_section(self):
        html_content = "<html><body><div>No movie section</div></body></html>"
        metadata = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html(html_content)
        assert metadata is None

    def test_handles_missing_fields_gracefully(self):
        html_content = """
        <section class="pelicula">
            <div class="InfoPelicula">
                <h2>Minimal Movie</h2>
            </div>
        </section>
        """
        metadata = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html(html_content)
        assert metadata is not None
        assert metadata.title == "Minimal Movie"
        assert metadata.original_title is None
        assert metadata.duration_minutes is None
        assert metadata.release_date is None
        assert metadata.actors == []


class TestParseReleaseDateEdgeCases:
    def test_parses_all_spanish_months(self):
        months = [
            ("22/enero/2026", 1),
            ("22/febrero/2026", 2),
            ("22/marzo/2026", 3),
            ("22/abril/2026", 4),
            ("22/mayo/2026", 5),
            ("22/junio/2026", 6),
            ("22/julio/2026", 7),
            ("22/agosto/2026", 8),
            ("22/septiembre/2026", 9),
            ("22/octubre/2026", 10),
            ("22/noviembre/2026", 11),
            ("22/diciembre/2026", 12),
        ]
        for date_str, expected_month in months:
            date = CineproxScraperAndHTMLParser._parse_release_date(date_str)
            assert date is not None, f"Failed to parse {date_str}"
            assert date.month == expected_month

    def test_returns_none_for_invalid_date(self):
        date = CineproxScraperAndHTMLParser._parse_release_date("32/01/2026")
        assert date is None

    def test_returns_none_for_unknown_month(self):
        date = CineproxScraperAndHTMLParser._parse_release_date("22/unknownmonth/2026")
        assert date is None


class TestParseCalendarDateEdgeCases:
    def test_returns_none_for_invalid_format(self):
        date = CineproxScraperAndHTMLParser._parse_calendar_date("invalid", 2026)
        assert date is None

    def test_returns_none_for_unknown_month_abbreviation(self):
        date = CineproxScraperAndHTMLParser._parse_calendar_date("24 xyz", 2026)
        assert date is None

    def test_returns_none_for_invalid_day(self):
        date = CineproxScraperAndHTMLParser._parse_calendar_date("32 ene", 2026)
        assert date is None


class TestParseShowtimesEdgeCases:
    def test_returns_empty_for_non_matching_theater(self):
        html_content = """
        <div class="accordion-item">
            <button class="accordion-button">Different Theater</button>
            <div class="accordion-collapse">
                <div class="tab-pane">
                    <div class="col-sm-6">
                        <div class="movie-schedule-header">2D - DOB</div>
                        <div class="movie-schedule-card">
                            <div class="movie-schedule-time">4:00 pm</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
        """
        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Target Theater",
        )
        assert showtimes == []

    def test_returns_empty_when_no_accordion_items(self):
        html_content = "<html><body><div>No accordions</div></body></html>"
        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Any Theater",
        )
        assert showtimes == []


class TestParseAvailableDatesEdgeCases:
    def test_returns_empty_when_no_calendar_container(self):
        html_content = "<html><body><div>No calendar</div></body></html>"
        dates = CineproxScraperAndHTMLParser.parse_available_dates_from_detail_html(html_content, 2026)
        assert dates == []


class TestIsTheaterAccordionExpandedEdgeCases:
    def test_returns_false_when_no_accordions(self):
        html_content = "<html><body><div>No accordions</div></body></html>"
        is_expanded = CineproxScraperAndHTMLParser.is_theater_accordion_expanded(html_content, "Any Theater")
        assert is_expanded is False

    def test_returns_false_when_theater_not_found(self):
        html_content = """
        <div class="accordion-item">
            <button class="accordion-button">Different Theater</button>
            <div class="accordion-collapse show"></div>
        </div>
        """
        is_expanded = CineproxScraperAndHTMLParser.is_theater_accordion_expanded(html_content, "Target Theater")
        assert is_expanded is False


# =============================================================================
# CineproxShowtimeSaver Tests
# =============================================================================


@pytest.mark.django_db
class TestCineproxShowtimeSaverValidateTheaterConfig:
    def test_returns_false_and_creates_issue_when_no_config(
        self, cineprox_theater_without_config, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        scraper = CineproxScraperAndHTMLParser()
        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)

        result = saver._validate_theater_config(cineprox_theater_without_config)

        assert result is False
        issue = OperationalIssue.objects.filter(name="Cineprox Missing Scraper Config").latest("created_at")
        assert "Theater Without Config" in issue.error_message

    def test_returns_false_and_creates_issue_when_incomplete_config(
        self, cineprox_theater_incomplete_config, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        scraper = CineproxScraperAndHTMLParser()
        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)

        result = saver._validate_theater_config(cineprox_theater_incomplete_config)

        assert result is False
        issue = OperationalIssue.objects.filter(name="Cineprox Incomplete Scraper Config").latest("created_at")
        assert "Theater Incomplete Config" in issue.error_message

    def test_returns_true_for_valid_config(
        self, cineprox_theater, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        scraper = CineproxScraperAndHTMLParser()
        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)

        result = saver._validate_theater_config(cineprox_theater)

        assert result is True


@pytest.mark.django_db
class TestCineproxShowtimeSaverFindMovies:
    def test_returns_empty_list_when_invalid_config(
        self, cineprox_theater_without_config, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        scraper = CineproxScraperAndHTMLParser()
        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)

        movies = saver._find_movies(cineprox_theater_without_config)

        assert movies == []

    def test_returns_movies_and_creates_issue_when_no_movies_found(
        self, cineprox_theater, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.return_value = "<html></html>"
        scraper.parse_movies_from_cartelera_html.return_value = []

        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)
        initial_count = OperationalIssue.objects.count()

        movies = saver._find_movies(cineprox_theater)

        assert movies == []
        assert OperationalIssue.objects.count() == initial_count + 1
        issue = OperationalIssue.objects.latest("created_at")
        assert issue.name == "Cineprox No Movies Found"

    def test_filters_pronto_movies_and_caches_cards(
        self, cineprox_theater, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.return_value = "<html></html>"
        scraper.parse_movies_from_cartelera_html.return_value = [
            CineproxMovieCard(movie_id="1", title="Active Movie", slug="active-movie", poster_url="", category="estrenos"),
            CineproxMovieCard(movie_id="2", title="Coming Soon", slug="coming-soon", poster_url="", category="pronto"),
        ]
        scraper.generate_movie_source_url.side_effect = lambda mid, slug: f"https://cineprox.com/{mid}-{slug}"

        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)

        movies = saver._find_movies(cineprox_theater)

        assert len(movies) == 1
        assert movies[0].name == "Active Movie"
        assert "https://cineprox.com/1-active-movie" in saver._movie_cards_cache


@pytest.mark.django_db
class TestCineproxShowtimeSaverFindMoviesForChain:
    def test_returns_movies_from_homepage(
        self, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        """Test _find_movies_for_chain fetches movies from the homepage."""
        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.return_value = "<html></html>"
        scraper.parse_movies_from_cartelera_html.return_value = [
            CineproxMovieCard(movie_id="1", title="Movie 1", slug="movie-1", poster_url="", category="estrenos"),
            CineproxMovieCard(movie_id="2", title="Movie 2", slug="movie-2", poster_url="", category="cartelera"),
        ]
        scraper.generate_movie_source_url.side_effect = lambda mid, slug: f"https://cineprox.com/{mid}-{slug}"

        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)

        movies = saver._find_movies_for_chain()

        assert len(movies) == 2
        scraper.download_cartelera_html.assert_called_once_with("https://www.cineprox.com/")

    def test_filters_pronto_movies(
        self, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        """Test _find_movies_for_chain excludes pronto (coming soon) movies."""
        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.return_value = "<html></html>"
        scraper.parse_movies_from_cartelera_html.return_value = [
            CineproxMovieCard(movie_id="1", title="Active", slug="active", poster_url="", category="estrenos"),
            CineproxMovieCard(movie_id="2", title="Coming Soon", slug="coming-soon", poster_url="", category="pronto"),
        ]
        scraper.generate_movie_source_url.side_effect = lambda mid, slug: f"https://cineprox.com/{mid}-{slug}"

        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)

        movies = saver._find_movies_for_chain()

        assert len(movies) == 1
        assert movies[0].name == "Active"

    def test_creates_operational_issue_on_network_error(
        self, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        """Test _find_movies_for_chain handles network errors gracefully."""
        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.side_effect = Exception("Network error")

        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)
        initial_count = OperationalIssue.objects.count()

        movies = saver._find_movies_for_chain()

        assert movies == []
        assert OperationalIssue.objects.count() == initial_count + 1
        issue = OperationalIssue.objects.latest("created_at")
        assert issue.name == "Cineprox Homepage Download Failed"

    def test_creates_operational_issue_when_no_movies_found(
        self, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        """Test _find_movies_for_chain logs issue when no movies found."""
        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.return_value = "<html></html>"
        scraper.parse_movies_from_cartelera_html.return_value = []

        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)
        initial_count = OperationalIssue.objects.count()

        movies = saver._find_movies_for_chain()

        assert movies == []
        assert OperationalIssue.objects.count() == initial_count + 1
        issue = OperationalIssue.objects.latest("created_at")
        assert issue.name == "Cineprox No Movies on Homepage"

    def test_caches_movie_cards(
        self, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        """Test _find_movies_for_chain populates the movie card cache."""
        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.return_value = "<html></html>"
        scraper.parse_movies_from_cartelera_html.return_value = [
            CineproxMovieCard(movie_id="1", title="Movie", slug="movie", poster_url="/poster.jpg", category="estrenos"),
        ]
        scraper.generate_movie_source_url.return_value = "https://cineprox.com/1-movie"

        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)

        saver._find_movies_for_chain()

        assert "https://cineprox.com/1-movie" in saver._movie_cards_cache
        cached_card = saver._movie_cards_cache["https://cineprox.com/1-movie"]
        assert cached_card.title == "Movie"
        assert cached_card.poster_url == "/poster.jpg"


@pytest.mark.django_db
class TestCineproxShowtimeSaverExtractMetadata:
    def test_extracts_metadata_from_html(
        self, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        scraper = CineproxScraperAndHTMLParser()
        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)

        html_content = load_html_snapshot("cineprox___one_movie_for_one_theater.html")
        metadata = saver._extract_metadata("SIN PIEDAD", html_content)

        assert metadata is not None
        assert metadata.original_title == "MERCY"
        assert metadata.director == "Timur Bekmambetov"
        assert metadata.release_year == 2026
        assert metadata.duration_minutes == 100

    def test_returns_none_when_parsing_fails(
        self, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        scraper = CineproxScraperAndHTMLParser()
        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)

        metadata = saver._extract_metadata("Test Movie", "<html><body></body></html>")

        assert metadata is None


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

    def get_movie_details_side_effect(movie_id):
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
class TestCineproxShowtimeSaverIntegration:
    def test_full_execute_flow_with_single_movie(
        self, cineprox_theater, mock_storage_service_for_cineprox
    ):
        """Integration test: Full execute() flow with a single movie."""
        detail_html = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.return_value = "<html></html>"
        scraper.parse_movies_from_cartelera_html.return_value = [
            CineproxMovieCard(
                movie_id="123",
                title="SIN PIEDAD",
                slug="sin-piedad",
                poster_url="/poster.jpg",
                category="estrenos",
            ),
        ]
        scraper.download_movie_detail_html.return_value = detail_html
        scraper.parse_movie_metadata_from_detail_html = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html
        scraper.parse_showtimes_from_detail_html = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html
        scraper.parse_available_dates_from_detail_html = CineproxScraperAndHTMLParser.parse_available_dates_from_detail_html
        scraper.is_theater_accordion_expanded = CineproxScraperAndHTMLParser.is_theater_accordion_expanded
        scraper.generate_movie_source_url.return_value = "https://cineprox.com/123-sin-piedad"
        scraper.generate_movie_detail_url.return_value = "https://cineprox.com/123-sin-piedad?date=2026-01-24"

        tmdb_service = _create_tmdb_service_with_unique_results()
        saver = CineproxShowtimeSaver(scraper, tmdb_service, mock_storage_service_for_cineprox)

        report = saver.execute()

        assert report.total_showtimes > 0
        assert Showtime.objects.filter(theater=cineprox_theater).exists()
        assert Movie.objects.exists()

    def test_execute_for_single_theater_with_single_movie(
        self, cineprox_theater, mock_storage_service_for_cineprox
    ):
        """Test execute_for_theater() processes a single theater with a single movie."""
        detail_html = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.return_value = "<html></html>"
        scraper.parse_movies_from_cartelera_html.return_value = [
            CineproxMovieCard(
                movie_id="123",
                title="SIN PIEDAD",
                slug="sin-piedad",
                poster_url="/poster.jpg",
                category="estrenos",
            ),
        ]
        scraper.download_movie_detail_html.return_value = detail_html
        scraper.parse_movie_metadata_from_detail_html = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html
        scraper.parse_showtimes_from_detail_html = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html
        scraper.parse_available_dates_from_detail_html = CineproxScraperAndHTMLParser.parse_available_dates_from_detail_html
        scraper.is_theater_accordion_expanded = CineproxScraperAndHTMLParser.is_theater_accordion_expanded
        scraper.generate_movie_source_url.return_value = "https://cineprox.com/123-sin-piedad"
        scraper.generate_movie_detail_url.return_value = "https://cineprox.com/123-sin-piedad?date=2026-01-24"

        tmdb_service = _create_tmdb_service_with_unique_results()
        saver = CineproxShowtimeSaver(scraper, tmdb_service, mock_storage_service_for_cineprox)

        showtimes_count = saver.execute_for_theater(cineprox_theater)

        assert showtimes_count > 0
        assert Showtime.objects.filter(theater=cineprox_theater).count() == showtimes_count

    def test_handles_theater_processing_error_gracefully(
        self, cineprox_theater, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox
    ):
        """Test that errors during theater processing are caught and logged."""
        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.side_effect = Exception("Network error")

        saver = CineproxShowtimeSaver(scraper, mock_tmdb_service_for_cineprox, mock_storage_service_for_cineprox)
        initial_count = OperationalIssue.objects.count()

        report = saver.execute()

        assert report.total_showtimes == 0
        assert OperationalIssue.objects.count() > initial_count

    def test_creates_movie_source_url_link(
        self, cineprox_theater, mock_storage_service_for_cineprox
    ):
        """Test that MovieSourceUrl is created linking movie to scraper URL."""
        detail_html = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.return_value = "<html></html>"
        scraper.parse_movies_from_cartelera_html.return_value = [
            CineproxMovieCard(
                movie_id="123",
                title="SIN PIEDAD",
                slug="sin-piedad",
                poster_url="/poster.jpg",
                category="estrenos",
            ),
        ]
        scraper.download_movie_detail_html.return_value = detail_html
        scraper.parse_movie_metadata_from_detail_html = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html
        scraper.parse_showtimes_from_detail_html = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html
        scraper.parse_available_dates_from_detail_html = CineproxScraperAndHTMLParser.parse_available_dates_from_detail_html
        scraper.is_theater_accordion_expanded = CineproxScraperAndHTMLParser.is_theater_accordion_expanded
        scraper.generate_movie_source_url.return_value = "https://cineprox.com/123-sin-piedad"
        scraper.generate_movie_detail_url.return_value = "https://cineprox.com/123-sin-piedad?date=2026-01-24"

        tmdb_service = _create_tmdb_service_with_unique_results()
        saver = CineproxShowtimeSaver(scraper, tmdb_service, mock_storage_service_for_cineprox)
        saver.execute()

        assert MovieSourceUrl.objects.filter(scraper_type=MovieSourceUrl.ScraperType.CINEPROX).exists()

    def test_deletes_existing_showtimes_before_saving_new(
        self, cineprox_theater, mock_storage_service_for_cineprox
    ):
        """Test that existing showtimes are deleted before saving new ones."""
        detail_html = load_html_snapshot("cineprox___one_movie_for_one_theater.html")

        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.return_value = "<html></html>"
        scraper.parse_movies_from_cartelera_html.return_value = [
            CineproxMovieCard(
                movie_id="123",
                title="SIN PIEDAD",
                slug="sin-piedad",
                poster_url="/poster.jpg",
                category="estrenos",
            ),
        ]
        scraper.download_movie_detail_html.return_value = detail_html
        scraper.parse_movie_metadata_from_detail_html = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html
        scraper.parse_showtimes_from_detail_html = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html
        scraper.parse_available_dates_from_detail_html = CineproxScraperAndHTMLParser.parse_available_dates_from_detail_html
        scraper.is_theater_accordion_expanded = CineproxScraperAndHTMLParser.is_theater_accordion_expanded
        scraper.generate_movie_source_url.return_value = "https://cineprox.com/123-sin-piedad"
        scraper.generate_movie_detail_url.return_value = "https://cineprox.com/123-sin-piedad?date=2026-01-24"

        tmdb_service = _create_tmdb_service_with_unique_results()
        saver = CineproxShowtimeSaver(scraper, tmdb_service, mock_storage_service_for_cineprox)

        saver.execute()
        first_count = Showtime.objects.filter(theater=cineprox_theater).count()

        tmdb_service_2 = _create_tmdb_service_with_unique_results()
        saver2 = CineproxShowtimeSaver(scraper, tmdb_service_2, mock_storage_service_for_cineprox)
        saver2.execute()
        second_count = Showtime.objects.filter(theater=cineprox_theater).count()

        assert first_count == second_count


@pytest.mark.django_db
class TestCineproxShowtimeSaverMovieDeduplication:
    def test_does_not_lookup_movie_twice_across_theaters(
        self, mock_storage_service_for_cineprox, db
    ):
        """Test movie deduplication: same movie at multiple theaters only looked up once."""
        Theater.objects.create(
            slug="theater-1",
            name="Theater 1",
            chain="Cineprox",
            address="Address 1",
            city="City",
            is_active=True,
            scraper_type="cineprox",
            download_source_url="https://cineprox.com/theater1",
            scraper_config={"city_id": "1", "theater_id": "1"},
        )
        Theater.objects.create(
            slug="theater-2",
            name="Theater 2",
            chain="Cineprox",
            address="Address 2",
            city="City",
            is_active=True,
            scraper_type="cineprox",
            download_source_url="https://cineprox.com/theater2",
            scraper_config={"city_id": "2", "theater_id": "2"},
        )

        scraper = MagicMock(spec=CineproxScraperAndHTMLParser)
        scraper.download_cartelera_html.return_value = "<html></html>"
        scraper.parse_movies_from_cartelera_html.return_value = [
            CineproxMovieCard(movie_id="123", title="Same Movie", slug="same-movie", poster_url="", category="cartelera"),
        ]
        scraper.generate_movie_source_url.return_value = "https://cineprox.com/123-same-movie"
        scraper.generate_movie_detail_url.return_value = "https://cineprox.com/123-same-movie?params"
        scraper.download_movie_detail_html.return_value = load_html_snapshot("cineprox___one_movie_for_one_theater.html")
        scraper.parse_movie_metadata_from_detail_html = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html
        scraper.parse_showtimes_from_detail_html.return_value = []
        scraper.parse_available_dates_from_detail_html.return_value = []
        scraper.is_theater_accordion_expanded.return_value = True

        mock_tmdb = _create_tmdb_service_with_unique_results()
        saver = CineproxShowtimeSaver(scraper, mock_tmdb, mock_storage_service_for_cineprox)

        saver.execute()

        assert mock_tmdb.search_movie.call_count == 1

