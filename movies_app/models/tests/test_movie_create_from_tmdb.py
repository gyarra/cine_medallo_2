"""
Tests for Movie.create_from_tmdb method.
"""

import pytest

from movies_app.models import Movie
from movies_app.services.tmdb_service import TMDBMovieResult


@pytest.fixture
def tmdb_result():
    """Create a TMDBMovieResult for testing."""
    return TMDBMovieResult(
        id=12345,
        title="Película de TMDB",
        original_title="TMDB Movie Original",
        overview="A test movie from TMDB",
        release_date="2025-06-15",
        popularity=100.0,
        vote_average=7.5,
        vote_count=1000,
        poster_path=None,
        backdrop_path=None,
        genre_ids=[28, 12],
        original_language="en",
        adult=False,
        video=False,
    )


class TestCreateFromTmdb:
    @pytest.mark.django_db
    def test_title_override_is_used_when_provided(self, tmdb_result):
        """When title_override is provided, it should be used for title_es instead of TMDB title."""
        scraped_title = "Título del Teatro Local"

        movie = Movie.create_from_tmdb(
            tmdb_result=tmdb_result,
            tmdb_service=None,
            storage_service=None,
            title_override=scraped_title,
        )

        assert movie.title_es == scraped_title
        assert movie.title_es != tmdb_result.title

    @pytest.mark.django_db
    def test_tmdb_title_is_used_when_no_override(self, tmdb_result):
        """When title_override is None, TMDB title should be used for title_es."""
        movie = Movie.create_from_tmdb(
            tmdb_result=tmdb_result,
            tmdb_service=None,
            storage_service=None,
            title_override=None,
        )

        assert movie.title_es == tmdb_result.title
        assert movie.title_es == "Película de TMDB"

    @pytest.mark.django_db
    def test_original_title_always_from_tmdb(self, tmdb_result):
        """Original title should always come from TMDB regardless of title_override."""
        scraped_title = "Título Diferente"

        movie = Movie.create_from_tmdb(
            tmdb_result=tmdb_result,
            tmdb_service=None,
            storage_service=None,
            title_override=scraped_title,
        )

        assert movie.original_title == tmdb_result.original_title
        assert movie.original_title == "TMDB Movie Original"

    @pytest.mark.django_db
    def test_other_fields_populated_correctly(self, tmdb_result):
        """Other movie fields should be populated from TMDB regardless of title_override."""
        scraped_title = "Título Local"

        movie = Movie.create_from_tmdb(
            tmdb_result=tmdb_result,
            tmdb_service=None,
            storage_service=None,
            title_override=scraped_title,
        )

        assert movie.tmdb_id == 12345
        assert movie.year == 2025
        assert movie.synopsis == "A test movie from TMDB"
        assert movie.tmdb_rating == pytest.approx(7.5, rel=0.01)
