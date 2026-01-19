"""
TMDB (The Movie Database) API Service

Service for querying movie information from themoviedb.org API.
"""

import logging
from dataclasses import dataclass

import requests
from django.conf import settings

logger = logging.getLogger(__name__)

TMDB_API_BASE_URL = "https://api.themoviedb.org/3"


@dataclass
class TMDBMovieResult:
    """Represents a movie result from TMDB API."""

    id: int
    title: str
    original_title: str
    overview: str
    release_date: str
    popularity: float
    vote_average: float
    vote_count: int
    poster_path: str | None
    backdrop_path: str | None
    genre_ids: list[int]
    original_language: str
    adult: bool
    video: bool


@dataclass
class TMDBSearchResponse:
    """Represents a search response from TMDB API."""

    page: int
    total_pages: int
    total_results: int
    results: list[TMDBMovieResult]


class TMDBServiceError(Exception):
    """Exception raised when TMDB API requests fail."""

    pass


class TMDBService:
    """
    Service for interacting with The Movie Database (TMDB) API.

    Requires TMDB_API_TOKEN to be set in Django settings.
    """

    def __init__(self):
        self.api_token = getattr(settings, "TMDB_READ_ACCESS_TOKEN", None)
        if not self.api_token:
            raise TMDBServiceError(
                "TMDB_READ_ACCESS_TOKEN not configured in settings. "
                "Get your API token from https://www.themoviedb.org/settings/api"
            )

    def _get_headers(self) -> dict[str, str]:
        """Get headers for TMDB API requests."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "accept": "application/json",
        }

    def _make_request(self, endpoint: str, params: dict | None = None) -> dict:
        """
        Make a GET request to the TMDB API.

        Args:
            endpoint: API endpoint path (e.g., "/search/movie")
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            TMDBServiceError: If the request fails
        """
        url = f"{TMDB_API_BASE_URL}{endpoint}"

        try:
            response = requests.get(
                url,
                headers=self._get_headers(),
                params=params,
                timeout=10,
            )
            response.raise_for_status()
            return response.json()
        except requests.exceptions.Timeout:
            logger.error("TMDB API request timed out: %s", url)
            raise TMDBServiceError("TMDB API request timed out")
        except requests.exceptions.HTTPError as e:
            logger.error("TMDB API HTTP error: %s - %s", e.response.status_code, e.response.text)
            raise TMDBServiceError(f"TMDB API error: {e.response.status_code}")
        except requests.exceptions.RequestException as e:
            logger.error("TMDB API request failed: %s", str(e))
            raise TMDBServiceError(f"TMDB API request failed: {str(e)}")

    def search_movie(
        self,
        query: str,
        language: str = "es-ES",
        page: int = 1,
        include_adult: bool = False,
        year: int | None = None,
    ) -> TMDBSearchResponse:
        """
        Search for movies by title.

        Args:
            query: Movie title to search for (in Spanish or any language)
            language: Language for results (default: "es-ES" for Spanish)
            page: Page number for paginated results (default: 1)
            include_adult: Include adult content (default: False)
            year: Filter by release year (optional)

        Returns:
            TMDBSearchResponse with search results

        Raises:
            TMDBServiceError: If the search fails
        """
        params = {
            "query": query,
            "language": language,
            "page": page,
            "include_adult": str(include_adult).lower(),
        }

        if year:
            params["year"] = str(year)

        logger.info("Searching TMDB for movie: '%s' (language=%s)", query, language)

        data = self._make_request("/search/movie", params)

        results = [
            TMDBMovieResult(
                id=movie["id"],
                title=movie.get("title", ""),
                original_title=movie.get("original_title", ""),
                overview=movie.get("overview", ""),
                release_date=movie.get("release_date", ""),
                popularity=movie.get("popularity", 0.0),
                vote_average=movie.get("vote_average", 0.0),
                vote_count=movie.get("vote_count", 0),
                poster_path=movie.get("poster_path"),
                backdrop_path=movie.get("backdrop_path"),
                genre_ids=movie.get("genre_ids", []),
                original_language=movie.get("original_language", ""),
                adult=movie.get("adult", False),
                video=movie.get("video", False),
            )
            for movie in data.get("results", [])
        ]

        return TMDBSearchResponse(
            page=data.get("page", 1),
            total_pages=data.get("total_pages", 0),
            total_results=data.get("total_results", 0),
            results=results,
        )

    def search_movie_spanish(self, movie_name: str, year: int | None = None) -> TMDBSearchResponse:
        """
        Search for a movie by its Spanish title.

        Convenience method that sets Spanish language by default.

        Args:
            movie_name: Movie title in Spanish
            year: Filter by release year (optional)

        Returns:
            TMDBSearchResponse with search results
        """
        return self.search_movie(query=movie_name, language="es-ES", year=year)

    def get_poster_url(self, poster_path: str | None, size: str = "w500") -> str | None:
        """
        Get the full URL for a movie poster.

        Args:
            poster_path: Poster path from movie result
            size: Image size (w92, w154, w185, w342, w500, w780, original)

        Returns:
            Full URL to the poster image, or None if no poster
        """
        if not poster_path:
            return None
        return f"https://image.tmdb.org/t/p/{size}{poster_path}"
