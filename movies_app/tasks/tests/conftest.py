"""
Pytest fixtures for task tests.
"""

from unittest.mock import MagicMock, patch

import pytest

from movies_app.models import Theater
from movies_app.services.tmdb_service import TMDBMovieResult, TMDBSearchResponse


@pytest.fixture
def mamm_theater(db):
    """Create the MAMM theater for tests."""
    theater, _ = Theater.objects.get_or_create(
        slug="museo-de-arte-moderno-de-medellin",
        defaults={
            "name": "Museo de Arte Moderno de Medellín",
            "chain": "",
            "address": "Cra 44 #19a-100, El Poblado, Medellín",
            "city": "Medellín",
            "neighborhood": "Ciudad del Río",
            "website": "https://www.elmamm.org/cine/#semana",
            "screen_count": 1,
            "is_active": True,
        },
    )
    return theater


@pytest.fixture
def mock_tmdb_service():
    """Mock TMDB service that returns predictable results."""
    mock = MagicMock()
    mock.search_movie.return_value = TMDBSearchResponse(
        page=1,
        total_pages=1,
        total_results=1,
        results=[
            TMDBMovieResult(
                id=12345,
                title="Test Movie",
                original_title="Test Movie Original",
                overview="A test movie",
                release_date="2025-01-01",
                popularity=100.0,
                vote_average=7.5,
                vote_count=1000,
                poster_path="/test_poster.jpg",
                backdrop_path="/test_backdrop.jpg",
                genre_ids=[28, 12],
                original_language="en",
                adult=False,
                video=False,
            )
        ],
    )
    return mock


@pytest.fixture(autouse=True)
def mock_storage_service():
    """Auto-mock storage service to prevent S3 uploads during tests."""
    with patch(
        "movies_app.services.movie_lookup_service.MovieLookupService.create_storage_service"
    ) as mock:
        mock.return_value = None
        yield mock


@pytest.fixture(autouse=True)
def mock_tmdb_for_tasks():
    """Auto-mock TMDB service for task tests to prevent real API calls."""
    mock_response = TMDBSearchResponse(
        page=1,
        total_pages=1,
        total_results=1,
        results=[
            TMDBMovieResult(
                id=99999,
                title="Mocked Movie",
                original_title="Mocked Movie Original",
                overview="A mocked movie for testing",
                release_date="2025-01-15",
                popularity=50.0,
                vote_average=6.5,
                vote_count=500,
                poster_path="/mocked_poster.jpg",
                backdrop_path="/mocked_backdrop.jpg",
                genre_ids=[18],
                original_language="es",
                adult=False,
                video=False,
            )
        ],
    )

    with patch("movies_app.services.tmdb_service.TMDBService") as mock_class:
        mock_instance = MagicMock()
        mock_instance.search_movie.return_value = mock_response
        mock_instance.get_movie_details.return_value = MagicMock(
            directors=[],
            cast=[],
            videos=None,
            release_dates=None,
        )
        mock_class.return_value = mock_instance
        yield mock_instance
