# Unfindable Movie URLs Cache

## Problem

When scraping movie showtimes from colombia.com, if a movie cannot be matched to TMDB, we create an `OperationalIssue` but continue attempting to look it up on every subsequent scrape. This results in:

- Hundreds of redundant TMDB API calls for the same movie title
- Wasted API quota
- Slower scrape times
- Repeated `OperationalIssue` creation for the same problem

## Solution

Create a table to track movie URLs that could not be matched to TMDB. Before making TMDB API calls, check if the URL is already in this table.

## Model

```python
class UnfindableMovieUrl(models.Model):
    url = models.URLField(unique=True)
    movie_title = models.CharField(max_length=500)
    original_title = models.CharField(max_length=500, null=True, blank=True)
    reason = models.CharField(max_length=100)  # e.g., "no_tmdb_results", "no_date_match"
    attempts = models.PositiveIntegerField(default=1)
    first_seen = models.DateTimeField(auto_now_add=True)
    last_seen = models.DateTimeField(auto_now=True)
```

### Field Notes

- `url`: The colombia.com movie page URL (e.g., `https://www.colombia.com/cine/cartelera/la-maldicion-de-evelyn/`)
- `movie_title`: The display title from colombia.com for debugging/admin
- `original_title`: Extracted original title if present, for debugging
- `reason`: Why the movie couldn't be matched (for categorization)
- `attempts`: How many times we've encountered this URL (useful for prioritizing manual fixes)
- `first_seen` / `last_seen`: Timestamps for tracking

## Reasons to Track

| Reason | Description |
|--------|-------------|
| `no_tmdb_results` | TMDB search returned zero results |
| `no_date_match` | TMDB results found but none matched the release year |
| `no_metadata` | Could not scrape metadata from colombia.com movie page |
| `missing_release_date` | No release date found in colombia.com metadata |

## Implementation

### 1. Check Before TMDB Lookup

In `_get_or_create_movie()`, before calling TMDB:

```python
# Check if this URL is already known to be unfindable
if UnfindableMovieUrl.objects.filter(url=movie_url).exists():
    logger.debug(f"Skipping TMDB lookup for known unfindable URL: {movie_url}")
    return None
```

### 2. Record Unfindable URLs

When we fail to match a movie, record it in `UnfindableMovieUrl` **and** create an `OperationalIssue` (for visibility in logs/alerts):

```python
UnfindableMovieUrl.objects.update_or_create(
    url=movie_url,
    defaults={
        "movie_title": movie_title,
        "original_title": original_title,
        "reason": "no_tmdb_results",
        "attempts": F("attempts") + 1,
    }
)

OperationalIssue.objects.create(
    name="Unfindable Movie URL",
    task="_get_or_create_movie",
    error_message=f"Could not match movie to TMDB: {movie_title}",
    context={"movie_url": movie_url, "reason": "no_tmdb_results"},
    severity=OperationalIssue.Severity.WARNING,
)
```

### 3. Admin Interface

Register with Django admin for manual review:

- List view showing URL, title, reason, attempts, last_seen
- Filter by reason
- Action to delete entries (to retry matching)
- Action to manually link to a Movie (stretch goal)

### 4. Management Command (Optional)

`clear_unfindable_urls` command to:
- Clear all entries (force retry all)
- Clear entries older than N days
- Clear entries by reason

## Edge Cases

### Movie Later Added to TMDB

A movie might not be in TMDB today but could be added later. Options:

1. **Manual clearing**: Admin deletes the entry when they know the movie is now available
2. **TTL-based retry**: Clear entries older than 30 days and retry (not recommended - adds complexity)
3. **Accept the limitation**: Rarely needed, manual intervention is fine

**Recommendation**: Option 1 (manual clearing) is simplest and sufficient for an internal tool.

### Same Movie, Different URLs

Colombia.com might have multiple URLs for the same movie (unlikely but possible). Each URL is tracked independently, which is correct behavior.

### URL Changes

If colombia.com changes a movie's URL, the old entry becomes stale. This is fine - it won't cause problems, just a dead entry in the table.

## Testing

1. **Unit test**: `_get_or_create_movie` returns `None` immediately for URLs in `UnfindableMovieUrl`
2. **Unit test**: Unfindable URL is recorded when TMDB returns no results
3. **Unit test**: `attempts` counter increments on repeated encounters
4. **Integration test**: Full scrape skips TMDB calls for known unfindable URLs

## Migration Notes

- New table, no data migration needed
- After deployment, first scrape will still hit TMDB for all unfindable movies (populating the cache)
- Subsequent scrapes will benefit from the cache
