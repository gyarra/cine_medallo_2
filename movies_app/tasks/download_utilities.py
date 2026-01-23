"""
Common utilities for movie download tasks.

This module contains shared functionality used by multiple scrapers
(colombia.com, cine colombia, procinal, etc.) for:
- TMDB movie matching and lookup
- Storage service creation
- Movie creation and deduplication
"""

from __future__ import annotations

import datetime
import logging
import traceback
import unicodedata
from dataclasses import dataclass

from django.conf import settings

from movies_app.models import APICallCounter, Movie, OperationalIssue, UnfindableMovieUrl
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBMovieResult, TMDBService, TMDBServiceError

logger = logging.getLogger(__name__)


@dataclass
class MovieMetadata:
    """
    Metadata extracted from a movie listing source (colombia.com, etc.).

    Each scraper is responsible for parsing their source's date format
    into the standardized release_date and release_year fields.
    """

    genre: str
    duration_minutes: int | None
    classification: str
    director: str
    actors: list[str]
    original_title: str | None
    release_date: datetime.date | None
    release_year: int | None


@dataclass
class MovieLookupResult:
    """Result of attempting to find or create a movie."""

    movie: Movie | None
    is_new: bool
    tmdb_called: bool


@dataclass
class TaskReport:
    """Report of a download task's results."""

    total_showtimes: int
    tmdb_calls: int
    new_movies: list[str]

    def print_report(self) -> None:
        logger.info("\n\n")
        logger.info("=" * 50)
        logger.info("TASK REPORT")
        logger.info("=" * 50)
        logger.info(f"Total showtimes added: {self.total_showtimes}")
        logger.info(f"TMDB API calls made: {self.tmdb_calls}")
        logger.info(f"New movies added: {len(self.new_movies)}")
        if self.new_movies:
            for movie_title in self.new_movies:
                logger.info(f"  - {movie_title}")
        logger.info("=" * 50)


def create_storage_service() -> SupabaseStorageService | None:
    """Create a Supabase storage service if credentials are configured."""
    bucket_url = settings.SUPABASE_IMAGES_BUCKET_URL
    access_key_id = settings.SUPABASE_IMAGES_BUCKET_ACCESS_KEY_ID
    secret_access_key = settings.SUPABASE_IMAGES_BUCKET_SECRET_ACCESS_KEY
    bucket_name = settings.SUPABASE_IMAGES_BUCKET_NAME

    if not all([bucket_url, access_key_id, secret_access_key, bucket_name]):
        logger.debug("Supabase storage not configured, images will use TMDB URLs")
        return None

    return SupabaseStorageService(
        bucket_url=bucket_url,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        bucket_name=bucket_name,
    )


def normalize_name(name: str) -> str:
    """Normalize a name for comparison by lowercasing and removing accents/punctuation."""
    normalized = unicodedata.normalize("NFD", name.lower())
    return "".join(c for c in normalized if unicodedata.category(c) != "Mn").strip()


def record_unfindable_url(
    url: str,
    movie_title: str,
    original_title: str | None,
    reason: UnfindableMovieUrl.Reason,
    source_name: str,
) -> None:
    """
    Record a URL as unfindable to avoid future redundant lookups.

    Args:
        url: The URL that could not be matched
        movie_title: The title of the movie from the source
        original_title: The original title if available
        reason: Why the URL could not be matched
        source_name: Name of the source (e.g., "colombia.com", "cinecolombia")
    """
    obj, created = UnfindableMovieUrl.objects.update_or_create(
        url=url,
        defaults={
            "movie_title": movie_title,
            "original_title": original_title or "",
            "reason": reason,
        },
    )
    if not created:
        obj.attempts += 1
        obj.save(update_fields=["attempts"])

    OperationalIssue.objects.create(
        name="Unfindable Movie URL",
        task=f"get_or_create_movie ({source_name})",
        error_message=f"Could not match movie to TMDB: {movie_title}",
        context={"movie_url": url, "reason": reason, "original_title": original_title},
        severity=OperationalIssue.Severity.WARNING,
    )


def find_best_tmdb_match(
    results: list[TMDBMovieResult],
    movie_name: str,
    metadata: MovieMetadata | None,
    tmdb_service: TMDBService,
    source_name: str,
) -> TMDBMovieResult | None:
    """
    Find the best matching TMDB result using metadata for verification.

    Matching priority:
    1. Exact release date match
    2. Release year match (within 1 year tolerance)
    3. Director/actors match (fetches details from TMDB)
    4. Title similarity

    Args:
        results: List of TMDB search results
        movie_name: The movie name from the source listing
        metadata: Optional metadata from the source for matching
        tmdb_service: TMDB service instance for fetching details
        source_name: Name of the source for logging

    Returns:
        The best match, or None if no suitable match is found.
    """
    logger.debug(f"=== find_best_tmdb_match START for '{movie_name}' ===")
    logger.debug(f"  TMDB results count: {len(results)}")
    logger.debug(f"  Has metadata: {metadata is not None}")

    if not results:
        logger.debug("  No TMDB results, returning None")
        return None

    # If no metadata, fall back to first result
    if not metadata:
        logger.info(f"No metadata available for '{movie_name}', using first TMDB result")
        logger.debug(f"  Falling back to first result: '{results[0].title}' (id={results[0].id})")
        OperationalIssue.objects.create(
            name=f"No {source_name} Metadata",
            task="find_best_tmdb_match",
            error_message=f"Could not extract metadata from {source_name} for '{movie_name}'",
            context={"movie_name": movie_name},
            severity=OperationalIssue.Severity.WARNING,
        )
        return results[0]

    logger.debug(f"  Metadata: director='{metadata.director}', actors={metadata.actors}")
    logger.debug(f"  Metadata: release_date={metadata.release_date}, release_year={metadata.release_year}")

    source_date = metadata.release_date
    source_year = metadata.release_year
    logger.debug(f"  source_date={source_date}, source_year={source_year}")

    if not source_year:
        logger.warning(f"No release year in metadata for '{movie_name}'")
        OperationalIssue.objects.create(
            name=f"Missing {source_name} Release Date",
            task="find_best_tmdb_match",
            error_message=f"Could not get release date from {source_name} for '{movie_name}'",
            context={
                "movie_name": movie_name,
                "metadata": {
                    "genre": metadata.genre,
                    "duration_minutes": metadata.duration_minutes,
                    "director": metadata.director,
                },
            },
            severity=OperationalIssue.Severity.WARNING,
        )

    best_match: TMDBMovieResult | None = None
    best_score = -1
    has_date_match = False

    logger.debug(f"  --- Starting loop over {len(results)} TMDB results ---")

    for idx, result in enumerate(results):
        logger.debug(f"  [{idx}] Evaluating: '{result.title}' (id={result.id}, release={result.release_date})")
        score = 0

        # Parse TMDB date
        tmdb_date: datetime.date | None = None
        tmdb_year: int | None = None
        if result.release_date:
            try:
                tmdb_date = datetime.datetime.strptime(result.release_date, "%Y-%m-%d").date()
                tmdb_year = tmdb_date.year
            except ValueError:
                logger.debug(f"      Failed to parse TMDB date: '{result.release_date}'")

        logger.debug(f"      tmdb_date={tmdb_date}, tmdb_year={tmdb_year}")

        # Priority 1: Exact date match (strongest signal) - return immediately
        if source_date and tmdb_date and source_date == tmdb_date:
            logger.info(
                f"Exact date match for '{movie_name}': '{result.title}' "
                f"(id={result.id}, date={tmdb_date})"
            )
            logger.debug("  === EARLY RETURN: Exact date match ===")
            return result

        # Priority 2: Year match
        elif source_year and tmdb_year:
            year_diff = abs(source_year - tmdb_year)
            logger.debug(f"      Year comparison: source={source_year}, tmdb={tmdb_year}, diff={year_diff}")
            if year_diff == 0:
                score += 100
                has_date_match = True
                logger.debug("      +100 (same year)")
            elif year_diff == 1:
                # Allow 1 year difference for release timing differences between countries
                score += 50
                has_date_match = True
                logger.debug("      +50 (year diff = 1)")
            else:
                # Significant year mismatch is a strong negative signal
                score -= 50
                logger.debug("      -50 (year diff > 1)")

        # Title similarity bonus
        movie_name_lower = movie_name.lower()
        tmdb_title_lower = result.title.lower()
        original_title_lower = result.original_title.lower()

        if movie_name_lower == tmdb_title_lower:
            score += 30
            logger.debug("      +30 (exact title match)")
        elif movie_name_lower in tmdb_title_lower or tmdb_title_lower in movie_name_lower:
            score += 15
            logger.debug("      +15 (partial title match)")

        if movie_name_lower == original_title_lower:
            score += 20
            logger.debug("      +20 (exact original_title match)")
        elif movie_name_lower in original_title_lower or original_title_lower in movie_name_lower:
            score += 10
            logger.debug("      +10 (partial original_title match)")

        # Popularity boost (TMDB orders by relevance, so add small position-based bonus)
        position_bonus = max(0, 10 - idx)
        score += position_bonus
        logger.debug(f"      +{position_bonus} (position bonus)")

        # Director/actors matching - only fetch details if we have metadata to compare
        # and limit to top 5 results to avoid excessive API calls
        director_matched = False
        actor_matched = False
        if metadata and (metadata.director or metadata.actors) and idx < 5:
            logger.debug("      Fetching TMDB details for credits comparison...")
            try:
                APICallCounter.increment("tmdb")
                details = tmdb_service.get_movie_details(result.id, include_credits=True)
                logger.debug(f"      Got details: {len(details.directors)} directors, {len(details.cast) if details.cast else 0} cast")

                # Director matching
                if metadata.director and details.directors:
                    source_director = normalize_name(metadata.director)
                    tmdb_director_names = [d.name for d in details.directors]
                    logger.debug(f"      Director comparison: source='{source_director}', tmdb={tmdb_director_names}")
                    for tmdb_director in details.directors:
                        if normalize_name(tmdb_director.name) == source_director:
                            score += 150
                            director_matched = True
                            logger.debug(f"      +150 (director match: {tmdb_director.name})")
                            break

                # Actors matching - check if any source actor appears in TMDB cast
                if metadata.actors and details.cast:
                    source_actors = {normalize_name(a) for a in metadata.actors}
                    tmdb_actors = {normalize_name(c.name) for c in details.cast[:15]}  # Top 15 cast
                    matching_actors = source_actors & tmdb_actors
                    logger.debug(f"      Actor comparison: source={source_actors}")
                    logger.debug(f"      Actor comparison: tmdb={tmdb_actors}")
                    logger.debug(f"      Matching actors: {matching_actors}")
                    if matching_actors:
                        # Score based on number of matching actors
                        actor_score = min(len(matching_actors) * 30, 90)  # Cap at 90
                        score += actor_score
                        actor_matched = True
                        logger.debug(f"      +{actor_score} (actor match: {len(matching_actors)} actors)")
            except TMDBServiceError as e:
                logger.warning(f"Failed to fetch details for TMDB id {result.id}: {e}")
                OperationalIssue.objects.create(
                    name="TMDB Details Fetch Failed",
                    task="find_best_tmdb_match",
                    error_message=f"Failed to fetch TMDB details for movie id {result.id}: {e}",
                    context={"movie_name": movie_name, "tmdb_id": result.id, "tmdb_title": result.title},
                    severity=OperationalIssue.Severity.WARNING,
                )

        logger.debug(
            f"      FINAL SCORE: {score} (director_matched={director_matched}, actor_matched={actor_matched})"
        )

        if score > best_score:
            logger.debug(f"      New best match! (previous best_score={best_score})")
            best_score = score
            best_match = result

    logger.debug("  --- Loop complete ---")

    # Log operational issue if we couldn't match by date
    if not has_date_match and (source_date or source_year):
        tmdb_dates = [
            f"{r.title}: {r.release_date}" for r in results[:5]  # First 5 results
        ]
        logger.debug("  No date match found, creating OperationalIssue")
        OperationalIssue.objects.create(
            name="No TMDB Date Match",
            task="find_best_tmdb_match",
            error_message=f"No TMDB result matched release date for '{movie_name}'",
            context={
                "movie_name": movie_name,
                "source_date": str(source_date) if source_date else None,
                "source_year": source_year,
                "tmdb_results": tmdb_dates,
            },
            severity=OperationalIssue.Severity.WARNING,
        )

    if best_match:
        logger.info(
            f"Selected TMDB match for '{movie_name}': '{best_match.title}' "
            f"(id={best_match.id}, score={best_score}, date_matched={has_date_match})"
        )
        logger.debug(f"=== find_best_tmdb_match END: returning '{best_match.title}' ===")
    else:
        logger.warning(f"No suitable TMDB match found for '{movie_name}'")
        logger.debug("=== find_best_tmdb_match END: returning None ===")

    return best_match


def get_or_create_movie(
    movie_name: str,
    source_url: str | None,
    source_url_field: str,
    metadata: MovieMetadata | None,
    tmdb_service: TMDBService,
    storage_service: SupabaseStorageService | None,
    source_name: str,
) -> MovieLookupResult:
    """
    Get or create a movie, prioritizing lookup by source URL.

    This function handles:
    1. Looking up existing movies by source URL
    2. Checking if URLs are known to be unfindable
    3. Searching TMDB and finding the best match
    4. Creating new movies from TMDB data

    Args:
        movie_name: The movie name from the source listing
        source_url: URL to the movie on the source site (e.g., colombia.com movie page)
        source_url_field: Model field name for the source URL (e.g., "colombia_dot_com_url")
        metadata: Metadata extracted from the source (caller is responsible for scraping)
        tmdb_service: TMDB service instance
        storage_service: Optional Supabase storage service for image uploads
        source_name: Name of the source for logging (e.g., "colombia.com")

    Returns:
        MovieLookupResult with the movie (if found/created), whether it's new, and if TMDB was called
    """
    # Step 1: Try to find existing movie by source URL
    if source_url:
        existing_movie = Movie.objects.filter(**{source_url_field: source_url}).first()
        if existing_movie:
            return MovieLookupResult(movie=existing_movie, is_new=False, tmdb_called=False)

        # Step 1b: Check if this URL is already known to be unfindable
        unfindable = UnfindableMovieUrl.objects.filter(url=source_url).first()
        if unfindable:
            unfindable.attempts += 1
            unfindable.save(update_fields=["attempts", "last_seen"])
            logger.debug(f"Skipping TMDB lookup for known unfindable URL: {source_url}")
            return MovieLookupResult(movie=None, is_new=False, tmdb_called=False)

    # Step 2: Search TMDB (use original title if available for better matching)
    search_name = metadata.original_title if metadata and metadata.original_title else movie_name

    try:
        logger.info(f"Searching TMDB for: '{search_name}' (listing name: '{movie_name}')")
        APICallCounter.increment("tmdb")
        response = tmdb_service.search_movie(search_name)

        if not response.results:
            logger.warning(f"No TMDB results found for: {search_name}")
            if source_url:
                record_unfindable_url(
                    source_url,
                    movie_name,
                    metadata.original_title if metadata else None,
                    UnfindableMovieUrl.Reason.NO_TMDB_RESULTS,
                    source_name,
                )
            return MovieLookupResult(movie=None, is_new=False, tmdb_called=True)

        # Step 3: Find best matching TMDB result
        best_match = find_best_tmdb_match(response.results, movie_name, metadata, tmdb_service, source_name)
        if not best_match:
            if source_url:
                record_unfindable_url(
                    source_url,
                    movie_name,
                    metadata.original_title if metadata else None,
                    UnfindableMovieUrl.Reason.NO_MATCH,
                    source_name,
                )
            return MovieLookupResult(movie=None, is_new=False, tmdb_called=True)

        # Step 4: Check if this match already exists in DB
        existing_movie = Movie.objects.filter(tmdb_id=best_match.id).first()
        if existing_movie:
            # Add source URL if the movie doesn't have one yet
            if source_url and not getattr(existing_movie, source_url_field):
                setattr(existing_movie, source_url_field, source_url)
                existing_movie.save(update_fields=[source_url_field])
            return MovieLookupResult(movie=existing_movie, is_new=False, tmdb_called=True)

        # Step 5: Create new movie
        movie = Movie.create_from_tmdb(best_match, tmdb_service, storage_service)
        if source_url:
            setattr(movie, source_url_field, source_url)
            movie.save(update_fields=[source_url_field])

        logger.info(f"Created movie: {movie}")

        return MovieLookupResult(movie=movie, is_new=True, tmdb_called=True)

    except TMDBServiceError as e:
        logger.error(f"TMDB error for '{movie_name}': {e}")
        OperationalIssue.objects.create(
            name="TMDB API Error",
            task=f"get_or_create_movie ({source_name})",
            error_message=str(e),
            traceback=traceback.format_exc(),
            context={"movie_name": movie_name, "source_url": source_url},
            severity=OperationalIssue.Severity.ERROR,
        )
        return MovieLookupResult(movie=None, is_new=False, tmdb_called=True)
