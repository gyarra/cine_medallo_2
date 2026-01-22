import os
from unittest.mock import MagicMock, patch

import pytest


class TestExtractShowtimesFromHtml:
    def test_extracts_movie_names_from_colombia_dot_com_html(self):
        from movies_app.tasks.colombia_com_download_task import (
            _extract_showtimes_from_html,
        )

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "colombia_dot_com___vizcay_cine_colombia.html",
        )

        with open(html_snapshot_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        movie_showtimes = _extract_showtimes_from_html(html_content)
        movie_names = [ms.movie_name for ms in movie_showtimes]

        expected_movies = [
            "Avatar: Fuego Y Cenizas",
            "Exterminio: El Templo De Huesos",
            "Familia En Renta",
            "La Empleada",
            "La Única Opción",
            "Las Catadoras De Hitler",
            "Song Sung Blue: Sueño inquebrantable",
            "Valor Sentimental",
        ]

        assert movie_names == expected_movies

    def test_extracts_movie_urls_from_colombia_dot_com_html(self):
        from movies_app.tasks.colombia_com_download_task import (
            _extract_showtimes_from_html,
        )

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "colombia_dot_com___vizcay_cine_colombia.html",
        )

        with open(html_snapshot_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        movie_showtimes = _extract_showtimes_from_html(html_content)

        for ms in movie_showtimes:
            assert ms.movie_url is not None, f"Movie '{ms.movie_name}' should have a URL"
            assert ms.movie_url.startswith("https://www.colombia.com/cine/"), (
                f"Movie URL should start with colombia.com: {ms.movie_url}"
            )


class TestExtractMovieMetadata:
    def test_extracts_metadata_from_movie_page_html(self):
        from movies_app.tasks.colombia_com_download_task import (
            _extract_movie_metadata_from_html,
        )

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "colombia_dot_com___individual_movie.html",
        )

        with open(html_snapshot_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        metadata = _extract_movie_metadata_from_html(html_content)

        assert metadata is not None
        assert metadata.genre == "Terror"
        assert metadata.duration_minutes == 85
        assert metadata.classification == "18 Años"
        assert metadata.director == "Sasha Sibley"
        assert "Aleksa Palladino" in metadata.actors
        assert "Jadon Cal" in metadata.actors
        assert "Sean Bridgers" in metadata.actors
        assert "Ene 15 / 2026" in metadata.release_date
        assert metadata.original_title == "The Painted"  # From "La Maldición De Evelyn (The Painted)"

    def test_extracts_original_title_from_parentheses(self):
        from movies_app.tasks.colombia_com_download_task import (
            _extract_movie_metadata_from_html,
        )

        html_with_original_title = """
        <html>
        <h1>La Empleada (The Housemaid)</h1>
        <div class="pelicula">
            <div>Género: Drama</div>
            <div>Duración: 120 minutos</div>
            <div>Director: Test Director</div>
        </div>
        </html>
        """

        metadata = _extract_movie_metadata_from_html(html_with_original_title)

        assert metadata is not None
        assert metadata.original_title == "The Housemaid"

    def test_no_original_title_when_no_parentheses(self):
        from movies_app.tasks.colombia_com_download_task import (
            _extract_movie_metadata_from_html,
        )

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "colombia_dot_com___individual_movie_no_parens_title.html",
        )

        with open(html_snapshot_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        metadata = _extract_movie_metadata_from_html(html_content)

        assert metadata is not None
        assert metadata.original_title is None  # "Bugonia" has no parentheses

    def test_parse_release_year_from_colombia_date(self):
        from movies_app.tasks.colombia_com_download_task import (
            _parse_release_year_from_colombia_date,
        )

        assert _parse_release_year_from_colombia_date("Ene 15 / 2026") == 2026
        assert _parse_release_year_from_colombia_date("Dic 25 / 2025") == 2025
        assert _parse_release_year_from_colombia_date("") is None
        assert _parse_release_year_from_colombia_date("Invalid") is None

    def test_parse_release_date_from_colombia_date(self):
        import datetime

        from movies_app.tasks.colombia_com_download_task import (
            _parse_release_date_from_colombia_date,
        )

        assert _parse_release_date_from_colombia_date("Ene 15 / 2026") == datetime.date(2026, 1, 15)
        assert _parse_release_date_from_colombia_date("Dic 25 / 2025") == datetime.date(2025, 12, 25)
        assert _parse_release_date_from_colombia_date("Mar 1 / 2024") == datetime.date(2024, 3, 1)
        assert _parse_release_date_from_colombia_date("Ago 31 / 2023") == datetime.date(2023, 8, 31)
        assert _parse_release_date_from_colombia_date("") is None
        assert _parse_release_date_from_colombia_date("Invalid") is None
        assert _parse_release_date_from_colombia_date("2026") is None  # Year only doesn't parse


@pytest.mark.django_db
class TestGetOrCreateMovie:
    """Tests for _get_or_create_movie function."""

    @pytest.fixture
    def mock_tmdb_service(self):
        """Create a mock TMDB service."""
        from movies_app.services.tmdb_service import (
            TMDBGenre,
            TMDBMovieDetails,
            TMDBProductionCompany,
        )

        mock = MagicMock()
        # Mock get_movie_details to return a proper TMDBMovieDetails
        mock.get_movie_details.return_value = TMDBMovieDetails(
            id=12345,
            title="Avatar: Fuego Y Cenizas",
            original_title="Avatar: Fire and Ash",
            overview="The third installment of the Avatar franchise.",
            release_date="2025-12-19",
            popularity=500.0,
            vote_average=8.0,
            vote_count=1000,
            poster_path="/avatar3.jpg",
            backdrop_path="/avatar3_backdrop.jpg",
            genres=[TMDBGenre(id=28, name="Acción"), TMDBGenre(id=12, name="Aventura")],
            original_language="en",
            adult=False,
            video=False,
            runtime=180,
            budget=400000000,
            revenue=0,
            status="Post Production",
            tagline="Return to Pandora",
            homepage="",
            imdb_id="tt1234567",
            production_companies=[
                TMDBProductionCompany(id=1, name="20th Century Studios", logo_path=None, origin_country="US")
            ],
            cast=None,
            crew=None,
            videos=None,
        )
        return mock

    @pytest.fixture
    def sample_tmdb_results(self):
        """Sample TMDB search results with multiple movies."""
        from movies_app.services.tmdb_service import TMDBMovieResult, TMDBSearchResponse

        results = [
            TMDBMovieResult(
                id=12345,
                title="Avatar: Fuego Y Cenizas",
                original_title="Avatar: Fire and Ash",
                overview="The third installment of the Avatar franchise.",
                release_date="2025-12-19",
                popularity=500.0,
                vote_average=8.0,
                vote_count=1000,
                poster_path="/avatar3.jpg",
                backdrop_path="/avatar3_backdrop.jpg",
                genre_ids=[28, 12, 878],
                original_language="en",
                adult=False,
                video=False,
            ),
            TMDBMovieResult(
                id=99999,
                title="Avatar",
                original_title="Avatar",
                overview="The original Avatar movie from 2009.",
                release_date="2009-12-18",
                popularity=200.0,
                vote_average=7.5,
                vote_count=25000,
                poster_path="/avatar.jpg",
                backdrop_path="/avatar_backdrop.jpg",
                genre_ids=[28, 12, 878],
                original_language="en",
                adult=False,
                video=False,
            ),
        ]
        return TMDBSearchResponse(
            page=1,
            total_pages=1,
            total_results=2,
            results=results,
        )

    def test_finds_existing_movie_by_url(self, mock_tmdb_service):
        """Happy path: movie exists and can be found by colombia_dot_com_url."""
        from movies_app.models import Movie
        from movies_app.tasks.colombia_com_download_task import _get_or_create_movie

        movie = Movie.objects.create(
            tmdb_id=12345,
            title_es="Avatar: Fuego Y Cenizas",
            original_title="Avatar: Fire and Ash",
            slug="avatar-fuego-y-cenizas",
            year=2025,
            colombia_dot_com_url="https://www.colombia.com/cine/peliculas/avatar-fuego-y-cenizas",
        )

        result = _get_or_create_movie(
            movie_name="Avatar: Fuego Y Cenizas",
            movie_url="https://www.colombia.com/cine/peliculas/avatar-fuego-y-cenizas",
            tmdb_service=mock_tmdb_service,
            storage_service=None,
        )

        assert result.movie == movie
        assert result.is_new is False
        assert result.tmdb_called is False
        mock_tmdb_service.search_movie.assert_not_called()

    def test_finds_existing_movie_by_tmdb_id_when_no_url(
        self, mock_tmdb_service, sample_tmdb_results
    ):
        """Movie exists in DB but doesn't have a URL - finds it via TMDB search."""
        from movies_app.models import Movie
        from movies_app.tasks.colombia_com_download_task import _get_or_create_movie

        movie = Movie.objects.create(
            tmdb_id=12345,
            title_es="Avatar: Fuego Y Cenizas",
            original_title="Avatar: Fire and Ash",
            slug="avatar-fuego-y-cenizas",
            year=2025,
            colombia_dot_com_url=None,
        )

        mock_tmdb_service.search_movie.return_value = sample_tmdb_results

        result = _get_or_create_movie(
            movie_name="Avatar: Fuego Y Cenizas",
            movie_url="https://www.colombia.com/cine/peliculas/avatar-fuego-y-cenizas",
            tmdb_service=mock_tmdb_service,
            storage_service=None,
        )

        assert result.movie == movie
        assert result.is_new is False
        assert result.tmdb_called is True
        mock_tmdb_service.search_movie.assert_called_once()

        movie.refresh_from_db()
        assert movie.colombia_dot_com_url == "https://www.colombia.com/cine/peliculas/avatar-fuego-y-cenizas"

    def test_creates_new_movie_when_not_in_db(self, mock_tmdb_service, sample_tmdb_results):
        """Movie does not exist in DB - creates new movie from best TMDB match."""
        from movies_app.models import Movie
        from movies_app.tasks.colombia_com_download_task import _get_or_create_movie

        mock_tmdb_service.search_movie.return_value = sample_tmdb_results

        with patch(
            "movies_app.tasks.colombia_com_download_task._scrape_movie_page_async"
        ) as mock_scrape:
            mock_scrape.return_value = "<html></html>"

            with patch(
                "movies_app.tasks.colombia_com_download_task._extract_movie_metadata_from_html"
            ) as mock_extract:
                from movies_app.tasks.colombia_com_download_task import MovieMetadata

                mock_extract.return_value = MovieMetadata(
                    genre="Ciencia Ficción",
                    duration_minutes=180,
                    classification="PG-13",
                    director="James Cameron",
                    actors=["Sam Worthington", "Zoe Saldaña"],
                    release_date="Dic 19 / 2025",
                    original_title=None,
                )

                result = _get_or_create_movie(
                    movie_name="Avatar: Fuego Y Cenizas",
                    movie_url="https://www.colombia.com/cine/peliculas/avatar-fuego-y-cenizas",
                    tmdb_service=mock_tmdb_service,
                    storage_service=None,
                )

        assert result.movie is not None
        assert result.is_new is True
        assert result.tmdb_called is True
        assert result.movie.tmdb_id == 12345
        assert result.movie.colombia_dot_com_url == "https://www.colombia.com/cine/peliculas/avatar-fuego-y-cenizas"

        db_movie = Movie.objects.get(tmdb_id=12345)
        assert db_movie is not None

    def test_selects_correct_movie_from_multiple_results_using_year(
        self, mock_tmdb_service, sample_tmdb_results
    ):
        """When TMDB returns multiple results, selects the one matching colombia.com release year."""
        from movies_app.tasks.colombia_com_download_task import _get_or_create_movie

        mock_tmdb_service.search_movie.return_value = sample_tmdb_results

        with patch(
            "movies_app.tasks.colombia_com_download_task._scrape_movie_page_async"
        ) as mock_scrape:
            mock_scrape.return_value = "<html></html>"

            with patch(
                "movies_app.tasks.colombia_com_download_task._extract_movie_metadata_from_html"
            ) as mock_extract:
                from movies_app.tasks.colombia_com_download_task import MovieMetadata

                # Metadata indicates 2025 release - should match first result (2025), not second (2009)
                mock_extract.return_value = MovieMetadata(
                    genre="Ciencia Ficción",
                    duration_minutes=180,
                    classification="PG-13",
                    director="James Cameron",
                    actors=["Sam Worthington"],
                    release_date="Dic 19 / 2025",
                    original_title=None,
                )

                result = _get_or_create_movie(
                    movie_name="Avatar",
                    movie_url="https://www.colombia.com/cine/peliculas/avatar",
                    tmdb_service=mock_tmdb_service,
                    storage_service=None,
                )

        assert result.movie is not None
        assert result.movie.tmdb_id == 12345  # Should pick 2025 Avatar, not 2009

    def test_no_tmdb_results_returns_none(self, mock_tmdb_service):
        """When TMDB returns no results, returns None movie."""
        from movies_app.services.tmdb_service import TMDBSearchResponse
        from movies_app.tasks.colombia_com_download_task import _get_or_create_movie

        mock_tmdb_service.search_movie.return_value = TMDBSearchResponse(
            page=1, total_pages=0, total_results=0, results=[]
        )

        result = _get_or_create_movie(
            movie_name="Nonexistent Movie XYZ123",
            movie_url="https://www.colombia.com/cine/peliculas/nonexistent",
            tmdb_service=mock_tmdb_service,
            storage_service=None,
        )

        assert result.movie is None
        assert result.is_new is False
        assert result.tmdb_called is True

    def test_no_tmdb_results_records_unfindable_url(self, mock_tmdb_service):
        """When TMDB returns no results, records the URL as unfindable."""
        from movies_app.models import UnfindableMovieUrl
        from movies_app.services.tmdb_service import TMDBSearchResponse
        from movies_app.tasks.colombia_com_download_task import _get_or_create_movie

        mock_tmdb_service.search_movie.return_value = TMDBSearchResponse(
            page=1, total_pages=0, total_results=0, results=[]
        )

        movie_url = "https://www.colombia.com/cine/peliculas/unfindable-movie"
        _get_or_create_movie(
            movie_name="Unfindable Movie",
            movie_url=movie_url,
            tmdb_service=mock_tmdb_service,
            storage_service=None,
        )

        unfindable = UnfindableMovieUrl.objects.get(url=movie_url)
        assert unfindable.movie_title == "Unfindable Movie"
        assert unfindable.reason == UnfindableMovieUrl.Reason.NO_TMDB_RESULTS
        assert unfindable.attempts == 1

    def test_skips_tmdb_lookup_for_known_unfindable_url(self, mock_tmdb_service):
        """When URL is already in unfindable cache, skips TMDB lookup entirely."""
        from movies_app.models import UnfindableMovieUrl
        from movies_app.tasks.colombia_com_download_task import _get_or_create_movie

        movie_url = "https://www.colombia.com/cine/peliculas/cached-unfindable"
        UnfindableMovieUrl.objects.create(
            url=movie_url,
            movie_title="Cached Unfindable Movie",
            reason=UnfindableMovieUrl.Reason.NO_TMDB_RESULTS,
            attempts=3,
        )

        result = _get_or_create_movie(
            movie_name="Cached Unfindable Movie",
            movie_url=movie_url,
            tmdb_service=mock_tmdb_service,
            storage_service=None,
        )

        assert result.movie is None
        assert result.tmdb_called is False
        mock_tmdb_service.search_movie.assert_not_called()

    def test_increments_attempts_for_known_unfindable_url(self, mock_tmdb_service):
        """When encountering a known unfindable URL, increments the attempts counter."""
        from movies_app.models import UnfindableMovieUrl
        from movies_app.tasks.colombia_com_download_task import _get_or_create_movie

        movie_url = "https://www.colombia.com/cine/peliculas/repeat-unfindable"
        UnfindableMovieUrl.objects.create(
            url=movie_url,
            movie_title="Repeat Unfindable Movie",
            reason=UnfindableMovieUrl.Reason.NO_TMDB_RESULTS,
            attempts=5,
        )

        _get_or_create_movie(
            movie_name="Repeat Unfindable Movie",
            movie_url=movie_url,
            tmdb_service=mock_tmdb_service,
            storage_service=None,
        )

        unfindable = UnfindableMovieUrl.objects.get(url=movie_url)
        assert unfindable.attempts == 6
