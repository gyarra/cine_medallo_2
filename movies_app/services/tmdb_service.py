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
class TMDBGenre:
    """Represents a genre from TMDB API."""

    id: int
    name: str


@dataclass
class TMDBProductionCompany:
    """Represents a production company from TMDB API."""

    id: int
    name: str
    logo_path: str | None
    origin_country: str


@dataclass
class TMDBCastMember:
    """Represents a cast member (actor) from TMDB API."""

    id: int
    name: str
    character: str
    order: int
    profile_path: str | None


@dataclass
class TMDBCrewMember:
    """Represents a crew member from TMDB API."""

    id: int
    name: str
    job: str
    department: str
    profile_path: str | None


@dataclass
class TMDBVideo:
    """Represents a video (trailer, teaser, etc.) from TMDB API."""

    id: str
    key: str
    name: str
    site: str
    size: int
    type: str
    official: bool
    iso_639_1: str
    iso_3166_1: str
    published_at: str

    @property
    def youtube_url(self) -> str | None:
        """Get YouTube URL if this video is hosted on YouTube."""
        if self.site == "YouTube":
            return f"https://www.youtube.com/watch?v={self.key}"
        return None


@dataclass
class TMDBReleaseDateEntry:
    """Represents a release date entry with certification for a country."""

    iso_3166_1: str
    certification: str
    release_date: str
    type: int


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
class TMDBMovieDetails:
    """Represents detailed movie information from TMDB API."""

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
    genres: list[TMDBGenre]
    original_language: str
    adult: bool
    video: bool
    runtime: int | None
    budget: int
    revenue: int
    status: str
    tagline: str
    homepage: str
    imdb_id: str | None
    production_companies: list[TMDBProductionCompany]
    cast: list[TMDBCastMember] | None
    crew: list[TMDBCrewMember] | None
    videos: list[TMDBVideo] | None
    certification: str | None

    @property
    def directors(self) -> list[TMDBCrewMember]:
        """Get all directors from the crew."""
        if not self.crew:
            return []
        return [c for c in self.crew if c.job == "Director"]

    def get_best_trailer(self) -> TMDBVideo | None:
        """
        Select the best trailer from available videos.

        Priority:
        1. Spanish language trailers (iso_639_1 == "es")
        2. Official trailers over unofficial
        3. Higher quality (size: 1080 > 720 > 480)
        4. English as fallback if no Spanish available

        Returns:
            Best matching TMDBVideo or None if no trailers available
        """
        if not self.videos:
            return None

        trailers = [v for v in self.videos if v.type == "Trailer" and v.site == "YouTube"]
        if not trailers:
            return None

        def trailer_score(video: TMDBVideo) -> tuple[int, int, int]:
            lang_score = 2 if video.iso_639_1 == "es" else (1 if video.iso_639_1 == "en" else 0)
            official_score = 1 if video.official else 0
            quality_score = video.size
            return (lang_score, official_score, quality_score)

        trailers.sort(key=trailer_score, reverse=True)
        return trailers[0]


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

        logger.debug(f"Full results from TMDB: {data}")

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

    def _extract_certification(self, release_dates_data: dict) -> str | None:
        """
        Extract certification from TMDB release_dates response.

        Prioritizes US certification, then CO (Colombia), then any available.
        Only considers theatrical release types (type 3) or premiere (type 1).
        """
        results = release_dates_data.get("results", [])
        certifications_by_country: dict[str, str] = {}

        for country_data in results:
            country_code = country_data.get("iso_3166_1", "")
            release_dates = country_data.get("release_dates", [])

            for rd in release_dates:
                cert = rd.get("certification", "").strip()
                release_type = rd.get("type", 0)
                # Type 3 = Theatrical, Type 1 = Premiere
                if cert and release_type in (1, 3):
                    certifications_by_country[country_code] = cert
                    break

        # Priority: US, then CO, then first available
        if "US" in certifications_by_country:
            return certifications_by_country["US"]
        if "CO" in certifications_by_country:
            return certifications_by_country["CO"]
        if certifications_by_country:
            return next(iter(certifications_by_country.values()))
        return None

    def get_movie_details(
        self,
        tmdb_id: int,
        language: str = "es-ES",
        include_credits: bool = False,
        include_videos: bool = False,
        include_release_dates: bool = False,
    ) -> TMDBMovieDetails:
        """
        Get detailed information for a specific movie by TMDB ID.

        Returns more detailed information than search results, including:
        runtime, budget, revenue, production companies, imdb_id, status, etc.

        Args:
            tmdb_id: The TMDB movie ID
            language: Language for results (default: "es-ES" for Spanish)
            include_credits: If True, includes cast and crew in single API call
            include_videos: If True, includes trailers and other videos in single API call
            include_release_dates: If True, includes release dates with certifications

        Returns:
            TMDBMovieDetails with full movie information

        Raises:
            TMDBServiceError: If the request fails
        """
        params: dict[str, str] = {"language": language}
        append_responses: list[str] = []
        if include_credits:
            append_responses.append("credits")
        if include_videos:
            append_responses.append("videos")
        if include_release_dates:
            append_responses.append("release_dates")
        if append_responses:
            params["append_to_response"] = ",".join(append_responses)

        logger.info(
            "Fetching TMDB movie details for ID: %d (language=%s, credits=%s, videos=%s)",
            tmdb_id,
            language,
            include_credits,
            include_videos,
        )

        data = self._make_request(f"/movie/{tmdb_id}", params)

        genres = [
            TMDBGenre(id=g["id"], name=g.get("name", ""))
            for g in data.get("genres", [])
        ]

        production_companies = [
            TMDBProductionCompany(
                id=pc["id"],
                name=pc.get("name", ""),
                logo_path=pc.get("logo_path"),
                origin_country=pc.get("origin_country", ""),
            )
            for pc in data.get("production_companies", [])
        ]

        cast: list[TMDBCastMember] | None = None
        crew: list[TMDBCrewMember] | None = None
        videos: list[TMDBVideo] | None = None

        if include_credits and "credits" in data:
            credits_data = data["credits"]
            cast = [
                TMDBCastMember(
                    id=c["id"],
                    name=c.get("name", ""),
                    character=c.get("character", ""),
                    order=c.get("order", 0),
                    profile_path=c.get("profile_path"),
                )
                for c in credits_data.get("cast", [])
            ]
            crew = [
                TMDBCrewMember(
                    id=c["id"],
                    name=c.get("name", ""),
                    job=c.get("job", ""),
                    department=c.get("department", ""),
                    profile_path=c.get("profile_path"),
                )
                for c in credits_data.get("crew", [])
            ]

        if include_videos and "videos" in data:
            videos_data = data["videos"]
            videos = [
                TMDBVideo(
                    id=v["id"],
                    key=v.get("key", ""),
                    name=v.get("name", ""),
                    site=v.get("site", ""),
                    size=v.get("size", 0),
                    type=v.get("type", ""),
                    official=v.get("official", False),
                    iso_639_1=v.get("iso_639_1", ""),
                    iso_3166_1=v.get("iso_3166_1", ""),
                    published_at=v.get("published_at", ""),
                )
                for v in videos_data.get("results", [])
            ]

        certification: str | None = None
        if include_release_dates and "release_dates" in data:
            certification = self._extract_certification(data["release_dates"])

        return TMDBMovieDetails(
            id=data["id"],
            title=data.get("title", ""),
            original_title=data.get("original_title", ""),
            overview=data.get("overview", ""),
            release_date=data.get("release_date", ""),
            popularity=data.get("popularity", 0.0),
            vote_average=data.get("vote_average", 0.0),
            vote_count=data.get("vote_count", 0),
            poster_path=data.get("poster_path"),
            backdrop_path=data.get("backdrop_path"),
            genres=genres,
            original_language=data.get("original_language", ""),
            adult=data.get("adult", False),
            video=data.get("video", False),
            runtime=data.get("runtime"),
            budget=data.get("budget", 0),
            revenue=data.get("revenue", 0),
            status=data.get("status", ""),
            tagline=data.get("tagline", ""),
            homepage=data.get("homepage", ""),
            imdb_id=data.get("imdb_id"),
            production_companies=production_companies,
            cast=cast,
            crew=crew,
            videos=videos,
            certification=certification,
        )
