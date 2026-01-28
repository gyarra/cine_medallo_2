"""
Pytest fixtures for task tests.
"""

import os
from unittest.mock import MagicMock, patch

import pytest

from movies_app.models import Theater


def load_html_snapshot(filename: str) -> str:
    """Load HTML snapshot file from the html_snapshot directory."""
    html_snapshot_path = os.path.join(
        os.path.dirname(__file__),
        "html_snapshot",
        filename,
    )
    with open(html_snapshot_path, encoding="utf-8") as f:
        return f.read()
from movies_app.services.tmdb_service import (
    TMDBGenre,
    TMDBMovieDetails,
    TMDBMovieResult,
    TMDBProductionCompany,
    TMDBSearchResponse,
)


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
    mock_service = MagicMock()
    mock_service.get_existing_url.return_value = None
    mock_service.upload_image_from_url.return_value = "https://mock-storage.example.com/test-image.jpg"
    mock_service.download_and_upload_from_url.return_value = "https://mock-storage.example.com/test-image.jpg"
    with patch(
        "movies_app.services.supabase_storage_service.SupabaseStorageService.create_from_settings"
    ) as mock:
        mock.return_value = mock_service
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

    mock_instance = MagicMock()
    mock_instance.search_movie.return_value = mock_response
    mock_instance.get_movie_details.return_value = TMDBMovieDetails(
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

    # Patch TMDBService where it's imported/used in task modules
    with patch("movies_app.tasks.mamm_download_task.TMDBService") as mamm_mock, \
         patch("movies_app.tasks.colombia_com_download_task.TMDBService") as colombia_mock, \
         patch("movies_app.tasks.cinemark_download_task.TMDBService") as cinemark_mock, \
         patch("movies_app.tasks.cine_colombia_download_task.TMDBService") as cine_colombia_mock, \
         patch("movies_app.tasks.colombo_americano_download_task.TMDBService") as colombo_mock:
        mamm_mock.return_value = mock_instance
        colombia_mock.return_value = mock_instance
        cinemark_mock.return_value = mock_instance
        cine_colombia_mock.return_value = mock_instance
        colombo_mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture(autouse=True)
def mock_mamm_fetch_html():
    """Auto-mock fetch_page_html for MAMM task tests to prevent real HTTP requests."""
    mock_html = """
    <html>
    <body>
        <h1 class="product_title">Test Movie Title</h1>
        <div class="woocommerce-product-details__short-description">
            <p>+15 | 120 min</p>
            <p>Director: Test Director</p>
            <p>2025 | Colombia</p>
            <p>This is a test synopsis for the movie that is longer than fifty characters.</p>
        </div>
        <div class="woocommerce-product-gallery__image">
            <img src="https://example.com/poster.jpg" />
        </div>
    </body>
    </html>
    """
    with patch("movies_app.tasks.mamm_download_task.fetch_page_html", return_value=mock_html):
        yield
