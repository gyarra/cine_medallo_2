"""
Integration tests for MovieLookupService.

These tests use the real TMDB API to fetch data, then mock TMDBService for deterministic results.
"""


import datetime

import pytest
from unittest.mock import MagicMock
import json
from movies_app.models import Movie, MovieSourceUrl
from movies_app.services.movie_lookup_service import MovieLookupService
from movies_app.services.tmdb_service import TMDBService, TMDBMovieResult
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.tasks.download_utilities import MovieMetadata


@pytest.fixture
def tmdb_service():
    # Return a real TMDBService instance (will be mocked in test)
    return TMDBService()

@pytest.fixture
def storage_service():
    # Use a MagicMock for storage service
    return MagicMock(spec=SupabaseStorageService)


@pytest.mark.django_db
def test_find_best_tmdb_match_real_data(tmdb_service, storage_service, monkeypatch):
    movie_name = "Inception"
    source_name = "test_source"
    service = MovieLookupService(tmdb_service, storage_service, source_name)
    # Load TMDB API response from JSON file
    with open("movies_app/services/tests/tmdb_inception_search_results.json") as f:
        # Skip comment line
        lines = f.readlines()
        json_data = json.loads("".join(line for line in lines if not line.strip().startswith("//")))
    # Patch tmdb_service.search_movie to return a mock response
    class MockResponse:
        def __init__(self, results):
            self.results = results
    results = [
        TMDBMovieResult(
            id=entry["id"],
            title=entry["title"],
            original_title=entry["original_title"],
            release_date=entry["release_date"],
            overview=entry["overview"],
            poster_path=entry.get("poster_path"),
            vote_average=entry.get("vote_average"),
            popularity=entry.get("popularity"),
            vote_count=entry.get("vote_count"),
            backdrop_path=entry.get("backdrop_path"),
            genre_ids=entry.get("genre_ids"),
            original_language=entry.get("original_language"),
            adult=entry.get("adult"),
            video=entry.get("video"),
        )
        for entry in json_data["results"]
    ]
    monkeypatch.setattr(tmdb_service, "search_movie", lambda q: MockResponse(results))
    response = tmdb_service.search_movie(movie_name)
    assert response.results, "TMDB should return results for a known movie"
    best = service.find_best_tmdb_match(response.results, movie_name, None)
    assert best is not None
    assert best.original_title.lower() == "inception"
    assert best.title == "Origen"

class TestMovieLookupService:
    @pytest.mark.django_db
    def test_normalize_title(self):
        assert Movie.normalize_title("José") == "jose"
        assert Movie.normalize_title("Café!") == "cafe!"
        assert Movie.normalize_title("  Movie Title  ") == "movie title"

    @pytest.mark.django_db
    def test_find_existing_movie_by_title_matches_title_es(self, tmdb_service, storage_service):
        """When a movie exists in DB with matching title_es, return it without calling TMDB."""
        Movie.objects.create(
            title_es="No Me Sigas",
            slug="no-me-sigas",
            original_title="Don't Follow Me",
            tmdb_id=999999,
        )
        service = MovieLookupService(tmdb_service, storage_service, "test_source")

        result = service.get_or_create_movie(
            movie_name="NO ME SIGAS",
            source_url="https://example.com/no-me-sigas",
            scraper_type=MovieSourceUrl.ScraperType.CINEPROX,
            metadata=None,
        )

        assert result.movie is not None
        assert result.movie.title_es == "No Me Sigas"
        assert result.is_new is False
        assert result.tmdb_called is False

    @pytest.mark.django_db
    def test_find_existing_movie_by_original_title(self, tmdb_service, storage_service):
        """When a movie exists with matching original_title, return it without calling TMDB."""
        Movie.objects.create(
            title_es="No Me Sigas",
            slug="no-me-sigas",
            original_title="Don't Follow Me",
            tmdb_id=999998,
        )
        service = MovieLookupService(tmdb_service, storage_service, "test_source")

        result = service.get_or_create_movie(
            movie_name="DON'T FOLLOW ME",
            source_url="https://example.com/dont-follow-me",
            scraper_type=MovieSourceUrl.ScraperType.CINEPROX,
            metadata=None,
        )

        assert result.movie is not None
        assert result.movie.title_es == "No Me Sigas"
        assert result.is_new is False
        assert result.tmdb_called is False

    @pytest.mark.django_db
    def test_find_existing_movie_uses_year_to_disambiguate(self, tmdb_service, storage_service):
        """When multiple movies have the same title, use year to pick the correct one."""
        Movie.objects.create(
            title_es="The Batman",
            slug="the-batman-1989",
            year=1989,
            tmdb_id=111111,
        )
        movie_2022 = Movie.objects.create(
            title_es="The Batman",
            slug="the-batman-2022",
            year=2022,
            tmdb_id=222222,
        )
        service = MovieLookupService(tmdb_service, storage_service, "test_source")

        metadata = MovieMetadata(
            genre="Action",
            duration_minutes=176,
            classification="PG-13",
            director="Matt Reeves",
            actors=["Robert Pattinson"],
            release_date=datetime.date(2022, 3, 4),
            release_year=2022,
            original_title=None,
            trailer_url=None,
        )

        result = service.get_or_create_movie(
            movie_name="The Batman",
            source_url="https://example.com/the-batman",
            scraper_type=MovieSourceUrl.ScraperType.CINEPROX,
            metadata=metadata,
        )

        assert result.movie is not None
        assert result.movie == movie_2022
        assert result.movie.year == 2022
        assert result.is_new is False
        assert result.tmdb_called is False

    @pytest.mark.django_db
    def test_falls_back_to_tmdb_when_multiple_titles_no_year_in_metadata(
        self, tmdb_service, storage_service, monkeypatch
    ):
        """When multiple movies match title but no year in metadata, fall back to TMDB.

        This tests the intended behavior: when we can't disambiguate between multiple
        candidates (no year metadata), we defer to TMDB's more sophisticated matching.
        """
        Movie.objects.create(
            title_es="The Batman",
            slug="the-batman-1989",
            year=1989,
            tmdb_id=111111,
        )
        Movie.objects.create(
            title_es="The Batman",
            slug="the-batman-2022",
            year=2022,
            tmdb_id=222222,
        )
        service = MovieLookupService(tmdb_service, storage_service, "test_source")

        from movies_app.services.tmdb_service import TMDBSearchResponse

        mock_response = TMDBSearchResponse(
            page=1,
            total_pages=0,
            total_results=0,
            results=[],
        )
        monkeypatch.setattr(tmdb_service, "search_movie", lambda q: mock_response)

        result = service.get_or_create_movie(
            movie_name="The Batman",
            source_url="https://example.com/the-batman-unknown-year",
            scraper_type=MovieSourceUrl.ScraperType.CINEPROX,
            metadata=None,
        )

        assert result.tmdb_called is True

    @pytest.mark.django_db
    def test_falls_back_to_tmdb_when_multiple_titles_no_year_match(
        self, tmdb_service, storage_service, monkeypatch
    ):
        """When multiple movies match title but year doesn't match, fall back to TMDB."""
        Movie.objects.create(
            title_es="The Batman",
            slug="the-batman-1989",
            year=1989,
            tmdb_id=111111,
        )
        Movie.objects.create(
            title_es="The Batman",
            slug="the-batman-2022",
            year=2022,
            tmdb_id=222222,
        )
        service = MovieLookupService(tmdb_service, storage_service, "test_source")

        metadata = MovieMetadata(
            genre="Action",
            duration_minutes=180,
            classification="PG-13",
            director="Someone New",
            actors=["New Actor"],
            release_date=datetime.date(2030, 1, 1),
            release_year=2030,
            original_title=None,
            trailer_url=None,
        )

        from movies_app.services.tmdb_service import TMDBSearchResponse

        mock_response = TMDBSearchResponse(
            page=1,
            total_pages=0,
            total_results=0,
            results=[],
        )
        monkeypatch.setattr(tmdb_service, "search_movie", lambda q: mock_response)

        result = service.get_or_create_movie(
            movie_name="The Batman",
            source_url="https://example.com/the-batman-2030",
            scraper_type=MovieSourceUrl.ScraperType.CINEPROX,
            metadata=metadata,
        )

        assert result.tmdb_called is True

    @pytest.mark.django_db
    def test_falls_back_to_tmdb_when_single_title_year_mismatch(
        self, tmdb_service, storage_service, monkeypatch
    ):
        """When single movie matches title but year doesn't match, fall back to TMDB."""
        Movie.objects.create(
            title_es="Inception",
            slug="inception",
            year=2010,
            tmdb_id=333333,
        )
        service = MovieLookupService(tmdb_service, storage_service, "test_source")

        metadata = MovieMetadata(
            genre="Sci-Fi",
            duration_minutes=148,
            classification="PG-13",
            director="Christopher Nolan",
            actors=["Leonardo DiCaprio"],
            release_date=datetime.date(2025, 6, 15),
            release_year=2025,
            original_title=None,
            trailer_url=None,
        )

        from movies_app.services.tmdb_service import TMDBSearchResponse

        mock_response = TMDBSearchResponse(
            page=1,
            total_pages=0,
            total_results=0,
            results=[],
        )
        monkeypatch.setattr(tmdb_service, "search_movie", lambda q: mock_response)

        result = service.get_or_create_movie(
            movie_name="Inception",
            source_url="https://example.com/inception-2025",
            scraper_type=MovieSourceUrl.ScraperType.CINEPROX,
            metadata=metadata,
        )

        assert result.tmdb_called is True
