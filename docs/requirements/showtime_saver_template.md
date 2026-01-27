# Movie and Showtime Saver Template Pattern

## Overview

Refactor scraper download tasks to use a Template Method pattern. Extract common functionality from individual scrapers (Cineprox, MAMM, Colombia.com) into a reusable `MovieAndShowtimeSaverTemplate` base class.

**Initial Scope:** Convert only `CineproxShowtimeSaver` to use the template.

## Goals

1. Reduce code duplication across scraper tasks
2. Standardize the showtime saving workflow
3. Make it easier to add new scrapers
4. Keep scraper-specific logic isolated in dedicated classes
5. Deduplicate movie lookups across theaters (same movie at multiple theaters only looked up once)

## Current State

Each scraper task (e.g., `CineproxShowtimeSaver`, `MAMMShowtimeSaver`) duplicates:
- Theater iteration and error handling
- Movie caching logic (`processed_movies` dict)
- TMDB call counting
- New movie tracking
- Atomic showtime saving with delete-then-insert
- `TaskReport` generation

## Design

### Class Hierarchy

```
MovieAndShowtimeSaverTemplate (abstract base class)
└── CineproxShowtimeSaver (initial implementation)
```

### MovieAndShowtimeSaverTemplate

Location: `movies_app/tasks/movie_and_showtime_saver_template.py`

**Responsibilities:**
- Iterate over theaters filtered by `scraper_type`
- Collect movies from all theaters, deduplicating lookups
- Track processed movies (caching)
- Count TMDB API calls
- Track new movies
- Generate `TaskReport`
- Atomic showtime saving (delete existing + insert new)

**Constructor Parameters:**
- `tmdb_service: TMDBService`
- `storage_service: SupabaseStorageService | None`
- `source_name: str` - Used for MovieLookupService
- `scraper_type: str` - Filter for `Theater.objects.filter(scraper_type=...)`

**Template Method:**

```python
def execute(self) -> TaskReport:
    """Main entry point. Finds movies across all theaters, then processes showtimes."""
    theaters = Theater.objects.filter(scraper_type=self.scraper_type)
    total_showtimes = 0
    movies_for_scraper: dict[str, Movie | None] = {}  # url -> Movie, cached across all theaters

    for theater in theaters:
        try:
            # Step 1: Find movies for this theater (returns list of tuples: name, url)
            movies_for_theater = self._find_movies(theater)

            # Step 2: Look up/create movies we haven't seen yet
            self._get_or_create_movies(movies_for_theater, movies_for_scraper)

            # Step 3: Process showtimes for this theater using cached movies
            showtimes_count = self._process_theater(theater, movies_for_scraper)
            total_showtimes += showtimes_count

        except Exception as e:
            self._handle_theater_error(theater, e)

    return TaskReport(
        total_showtimes=total_showtimes,
        tmdb_calls=self.tmdb_calls,
        new_movies=self.new_movies,
    )
```

**Abstract Methods (subclasses must implement):**

```python
@abstractmethod
def _find_movies(self, theater: Theater) -> list[tuple[str, str]]:
    """
    Find all movies showing at a theater.

    Returns: List of (movie_name, source_url) tuples.
    The source_url is used as the cache key for deduplication.
    """
    pass

@abstractmethod
def _get_movie_metadata(self, movie_name: str, source_url: str) -> MovieMetadata | None:
    """
    Fetch metadata for a movie from the scraper source.
    Called only for movies not already in cache.
    """
    pass

@abstractmethod
def _process_theater(self, theater: Theater, movies_cache: dict[str, Movie | None]) -> int:
    """
    Process showtimes for a theater.

    Use movies_cache to look up Movie objects by source_url.
    Returns: Number of showtimes saved.
    """
    pass
```

**Provided Methods (subclasses inherit):**

```python
def _get_or_create_movies(
    self,
    movies_for_theater: list[tuple[str, str]],
    movies_cache: dict[str, Movie | None],
) -> None:
    """
    Look up or create movies not already in cache.
    Updates movies_cache in place. Tracks TMDB calls and new movies.
    """
    for movie_name, source_url in movies_for_theater:
        if source_url in movies_cache:
            continue  # Already looked up

        # Check if already linked in database
        existing_movie = MovieSourceUrl.get_movie_for_source_url(
            url=source_url,
            scraper_type=self.scraper_type_enum,
        )
        if existing_movie:
            movies_cache[source_url] = existing_movie
            continue

        # Fetch metadata and look up via TMDB
        metadata = self._get_movie_metadata(movie_name, source_url)
        result = self.lookup_service.get_or_create_movie(
            movie_name=movie_name,
            source_url=source_url,
            scraper_type=self.scraper_type_enum,
            metadata=metadata,
        )

        movies_cache[source_url] = result.movie
        if result.tmdb_called:
            self.tmdb_calls += 1
        if result.is_new and result.movie:
            self.new_movies.append(result.movie.title_es)

def _save_showtimes_for_theater(
    self,
    theater: Theater,
    showtimes: list[ShowtimeData],
) -> int:
    """
    Atomic delete and insert of showtimes for a theater.
    Deletes all existing showtimes for theater, then inserts new ones.
    """
    pass

def _handle_theater_error(self, theater: Theater, error: Exception) -> None:
    """Log error and create OperationalIssue."""
    pass
```

### Data Classes

Add to `download_utilities.py`:

```python
@dataclass
class ShowtimeData:
    """Generic showtime data that all scrapers produce."""
    movie: Movie
    date: datetime.date
    time: datetime.time
    format: str
    translation_type: str
    screen: str
    source_url: str
```

### Scraper-Specific Classes

Each scraper keeps its own:
- HTML parser class (e.g., `CineproxScraperAndHTMLParser`)
- Dataclasses for scraper-specific structures (e.g., `CineproxMovieCard`, `CineproxShowtime`)
- Implementation of abstract methods

Example `CineproxShowtimeSaver`:

```python
class CineproxShowtimeSaver(MovieAndShowtimeSaverTemplate):
    def __init__(
        self,
        scraper: CineproxScraperAndHTMLParser,
        tmdb_service: TMDBService,
        storage_service: SupabaseStorageService | None,
    ):
        super().__init__(
            tmdb_service=tmdb_service,
            storage_service=storage_service,
            source_name="cineprox",
            scraper_type="cineprox",
        )
        self.scraper = scraper

    def _find_movies(self, theater: Theater) -> list[tuple[str, str]]:
        """Download cartelera and return list of (name, url) tuples."""
        # Validate theater config
        if not self._validate_theater_config(theater):
            return []

        html_content = self.scraper.download_cartelera_html(theater.download_source_url)
        movie_cards = self.scraper.parse_movies_from_cartelera_html(html_content)

        # Filter out "pronto" movies
        active_movies = [m for m in movie_cards if m.category != "pronto"]

        return [
            (card.title, self.scraper.generate_movie_source_url(card.movie_id, card.slug))
            for card in active_movies
        ]

    def _get_movie_metadata(self, movie_name: str, source_url: str) -> MovieMetadata | None:
        """Download movie detail page and extract metadata."""
        # Need to construct detail URL from source_url
        # Download and parse metadata
        pass

    def _process_theater(self, theater: Theater, movies_cache: dict[str, Movie | None]) -> int:
        """Parse showtimes and save them."""
        # For each movie, download detail page if needed
        # Parse showtimes
        # Build list of ShowtimeData
        # Call _save_showtimes_for_theater
        pass

    def _validate_theater_config(self, theater: Theater) -> bool:
        """Check scraper_config has city_id, theater_id, and download_source_url exists."""
        # Create OperationalIssue if invalid
        pass
```

## Implementation Plan

1. Create `MovieAndShowtimeSaverTemplate` base class with template method
2. Add `ShowtimeData` dataclass to `download_utilities.py`
3. Refactor `CineproxShowtimeSaver` to extend `MovieAndShowtimeSaverTemplate`
4. Add tests for the template class
5. Verify existing Cineprox tests still pass

## Testing

- Unit test `MovieAndShowtimeSaverTemplate` with a mock subclass
- Existing Cineprox scraper tests should continue to pass
- Integration test: run `cineprox_download_task` management command manually

## Files Changed

- New: `movies_app/tasks/movie_and_showtime_saver_template.py`
- Modified: `movies_app/tasks/download_utilities.py` (add `ShowtimeData` dataclass)
- Modified: `movies_app/tasks/cineprox_download_task.py`

## Notes

- The `scraper` class (e.g., `CineproxScraperAndHTMLParser`) remains scraper-specific and is not abstracted
- Each scraper may have different validation requirements for `Theater.scraper_config`
- `normalize_translation_type` should be called when building `ShowtimeData`, not in the template
- The two-phase approach (find movies, then process showtimes) allows movie deduplication across theaters
