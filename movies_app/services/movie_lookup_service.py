"""
MovieLookupService: Service for movie lookup, TMDB matching, and deduplication.
"""


import datetime
import logging
import traceback
import unicodedata
from django.conf import settings
from movies_app.models import APICallCounter, Movie, OperationalIssue, UnfindableMovieUrl
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBMovieResult, TMDBService, TMDBServiceError
from movies_app.services.movie_lookup_result import MovieLookupResult

logger = logging.getLogger(__name__)

class MovieLookupService:
    def __init__(self, tmdb_service: TMDBService, storage_service: SupabaseStorageService | None, source_name: str):
        self.tmdb_service = tmdb_service
        self.storage_service = storage_service
        self.source_name = source_name

    @staticmethod
    def create_storage_service() -> SupabaseStorageService | None:
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

    @staticmethod
    def normalize_name(name: str) -> str:
        normalized = unicodedata.normalize("NFD", name.lower())
        return "".join(c for c in normalized if unicodedata.category(c) != "Mn").strip()

    def record_unfindable_url(
        self,
        url: str,
        movie_title: str,
        original_title: str | None,
        reason: UnfindableMovieUrl.Reason,
    ) -> None:
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
            task=f"get_or_create_movie ({self.source_name})",
            error_message=f"Could not match movie to TMDB: {movie_title}",
            context={"movie_url": url, "reason": reason, "original_title": original_title},
            severity=OperationalIssue.Severity.WARNING,
        )


    def find_best_tmdb_match(
        self,
        results: list[TMDBMovieResult],
        movie_name: str,
        metadata,
    ) -> TMDBMovieResult | None:
        logger.debug(f"=== find_best_tmdb_match START for '{movie_name}' ===")
        logger.debug(f"  TMDB results count: {len(results)}")
        logger.debug(f"  Has metadata: {metadata is not None}")

        if not results:
            logger.debug("  No TMDB results, returning None")
            return None

        if not metadata:
            logger.info(f"No metadata available for '{movie_name}', using first TMDB result")
            logger.debug(f"  Falling back to first result: '{results[0].title}' (id={results[0].id})")
            OperationalIssue.objects.create(
                name=f"No {self.source_name} Metadata",
                task="find_best_tmdb_match",
                error_message=f"Could not extract metadata from {self.source_name} for '{movie_name}'",
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
                name=f"Missing {self.source_name} Release Date",
                task="find_best_tmdb_match",
                error_message=f"Could not get release date from {self.source_name} for '{movie_name}'",
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

            tmdb_date: datetime.date | None = None
            tmdb_year: int | None = None
            if result.release_date:
                try:
                    tmdb_date = datetime.datetime.strptime(result.release_date, "%Y-%m-%d").date()
                    tmdb_year = tmdb_date.year
                except ValueError:
                    logger.debug(f"      Failed to parse TMDB date: '{result.release_date}'")

            logger.debug(f"      tmdb_date={tmdb_date}, tmdb_year={tmdb_year}")

            if source_date and tmdb_date and source_date == tmdb_date:
                logger.info(
                    f"Exact date match for '{movie_name}': '{result.title}' "
                    f"(id={result.id}, date={tmdb_date})"
                )
                logger.debug("  === EARLY RETURN: Exact date match ===")
                return result

            elif source_year and tmdb_year:
                year_diff = abs(source_year - tmdb_year)
                logger.debug(f"      Year comparison: source={source_year}, tmdb={tmdb_year}, diff={year_diff}")
                if year_diff == 0:
                    score += 100
                    has_date_match = True
                    logger.debug("      +100 (same year)")
                elif year_diff == 1:
                    score += 50
                    has_date_match = True
                    logger.debug("      +50 (year diff = 1)")
                else:
                    score -= 50
                    logger.debug("      -50 (year diff > 1)")

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

            position_bonus = max(0, 10 - idx)
            score += position_bonus
            logger.debug(f"      +{position_bonus} (position bonus)")

            director_matched = False
            actor_matched = False
            if metadata and (metadata.director or metadata.actors) and idx < 5:
                logger.debug("      Fetching TMDB details for credits comparison...")
                try:
                    APICallCounter.increment("tmdb")
                    details = self.tmdb_service.get_movie_details(result.id, include_credits=True)
                    logger.debug(f"      Got details: {len(details.directors)} directors, {len(details.cast) if details.cast else 0} cast")

                    if metadata.director and details.directors:
                        source_director = self.normalize_name(metadata.director)
                        tmdb_director_names = [d.name for d in details.directors]
                        logger.debug(f"      Director comparison: source='{source_director}', tmdb={tmdb_director_names}")
                        for tmdb_director in details.directors:
                            if self.normalize_name(tmdb_director.name) == source_director:
                                score += 150
                                director_matched = True
                                logger.debug(f"      +150 (director match: {tmdb_director.name})")
                                break

                    if metadata.actors and details.cast:
                        source_actors = {self.normalize_name(a) for a in metadata.actors}
                        tmdb_actors = {self.normalize_name(c.name) for c in details.cast[:15]}
                        matching_actors = source_actors & tmdb_actors
                        logger.debug(f"      Actor comparison: source={source_actors}")
                        logger.debug(f"      Actor comparison: tmdb={tmdb_actors}")
                        logger.debug(f"      Matching actors: {matching_actors}")
                        if matching_actors:
                            actor_score = min(len(matching_actors) * 30, 90)
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

        if not has_date_match and (source_date or source_year):
            tmdb_dates = [
                f"{r.title}: {r.release_date}" for r in results[:5]
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
        self,
        movie_name: str,
        source_url: str | None,
        source_url_field: str,
        metadata,
    ):
        if source_url:
            existing_movie = Movie.objects.filter(**{source_url_field: source_url}).first()
            if existing_movie:
                return MovieLookupResult(movie=existing_movie, is_new=False, tmdb_called=False)

            unfindable = UnfindableMovieUrl.objects.filter(url=source_url).first()
            if unfindable:
                unfindable.attempts += 1
                unfindable.save(update_fields=["attempts", "last_seen"])
                logger.debug(f"Skipping TMDB lookup for known unfindable URL: {source_url}")
                return MovieLookupResult(movie=None, is_new=False, tmdb_called=False)

        search_name = metadata.original_title if metadata and getattr(metadata, "original_title", None) else movie_name

        try:
            logger.info(f"Searching TMDB for: '{search_name}' (listing name: '{movie_name}')")
            APICallCounter.increment("tmdb")
            response = self.tmdb_service.search_movie(search_name)

            if not response.results:
                logger.warning(f"No TMDB results found for: {search_name}")
                if source_url:
                    self.record_unfindable_url(
                        url=source_url,
                        movie_title=movie_name,
                        original_title=getattr(metadata, "original_title", None) if metadata else None,
                        reason=UnfindableMovieUrl.Reason.NO_TMDB_RESULTS,
                    )
                return MovieLookupResult(movie=None, is_new=False, tmdb_called=True)

            best_match = self.find_best_tmdb_match(response.results, movie_name, metadata)
            if not best_match:
                if source_url:
                    self.record_unfindable_url(
                        url=source_url,
                        movie_title=movie_name,
                        original_title=getattr(metadata, "original_title", None) if metadata else None,
                        reason=UnfindableMovieUrl.Reason.NO_MATCH,
                    )
                return MovieLookupResult(movie=None, is_new=False, tmdb_called=True)

            existing_movie = Movie.objects.filter(tmdb_id=best_match.id).first()
            if existing_movie:
                if source_url and not getattr(existing_movie, source_url_field):
                    setattr(existing_movie, source_url_field, source_url)
                    existing_movie.save(update_fields=[source_url_field])
                return MovieLookupResult(movie=existing_movie, is_new=False, tmdb_called=True)

            movie = Movie.create_from_tmdb(best_match, self.tmdb_service, self.storage_service)
            if source_url:
                setattr(movie, source_url_field, source_url)
                movie.save(update_fields=[source_url_field])

            logger.info(f"Created movie: {movie}")

            return MovieLookupResult(movie=movie, is_new=True, tmdb_called=True)

        except TMDBServiceError as e:
            logger.error(f"TMDB error for '{movie_name}': {e}")
            OperationalIssue.objects.create(
                name="TMDB API Error",
                task=f"get_or_create_movie ({self.source_name})",
                error_message=str(e),
                traceback=traceback.format_exc(),
                context={"movie_name": movie_name, "source_url": source_url},
                severity=OperationalIssue.Severity.ERROR,
            )
            return MovieLookupResult(movie=None, is_new=False, tmdb_called=True)
