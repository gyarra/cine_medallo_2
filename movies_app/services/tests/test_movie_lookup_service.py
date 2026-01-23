"""
Integration tests for MovieLookupService.

These tests use the real TMDB API to fetch data, then mock TMDBService for deterministic results.
"""


import pytest
from unittest.mock import MagicMock
import json
from movies_app.services.movie_lookup_service import MovieLookupService
from movies_app.services.tmdb_service import TMDBService, TMDBMovieResult
from movies_app.services.supabase_storage_service import SupabaseStorageService




@pytest.fixture
def tmdb_service():
    # Return a real TMDBService instance (will be mocked in test)
    return TMDBService()

@pytest.fixture
def storage_service():
    # Use a MagicMock for storage service
    return MagicMock(spec=SupabaseStorageService)

    # (removed duplicate, keep only the correct test below)
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

@pytest.mark.django_db
def test_normalize_name():
    assert MovieLookupService.normalize_name("José") == "jose"
    assert MovieLookupService.normalize_name("Café!") == "cafe!"
    assert MovieLookupService.normalize_name("  Movie Title  ") == "movie title"
