# Feature: Save Movie Details from TMDB

## Overview

When a new movie is discovered during the colombia.com scraping process, fetch complete details from TMDB and save them to the database. This includes trailer URLs, preferring Spanish-language trailers when available.

## Current State

The `Movie.create_from_tmdb()` method currently saves only basic fields from `TMDBMovieResult` (search result):
- `title_es`, `original_title`, `year`, `synopsis`, `poster_url`, `tmdb_id`, `tmdb_rating`

Missing data that TMDB provides:
- Runtime (`duration_minutes`)
- IMDb ID (`imdb_id`)
- Genres
- Director/cast
- Trailer URL
- Backdrop image

## Requirements

### 1. Fetch Full Movie Details

**When:** A new movie is created via `create_from_tmdb()` or `get_or_create_from_tmdb()`

**Action:** Call `TMDBService.get_movie_details()` with `append_to_response=videos,credits` to fetch:
- Runtime
- IMDb ID
- Genres (as comma-separated string or related model)
- Director name(s)
- Top billed cast
- Trailer videos

### 2. New Movie Model Fields

Add the following fields to the `Movie` model:

| Field | Type | Description |
|-------|------|-------------|
| `trailer_url` | URLField | YouTube trailer URL (nullable) |
| `backdrop_url` | URLField | TMDB backdrop image URL (nullable) |
| `director` | CharField | Director name(s) |
| `cast_summary` | CharField | Top 3-5 actors, comma-separated |

### 3. Genre Names in Spanish

TMDB returns localized genre names when `language=es-ES` is passed:
- "Action" → "Acción"
- "Science Fiction" → "Ciencia ficción"
- "Comedy" → "Comedia"

The existing `genre` field on `Movie` should be populated with Spanish genre names, comma-separated.

**Note:** `TMDBService.get_movie_details()` already defaults to `language="es-ES"`.

### 4. Trailer Selection Logic

When selecting a trailer from TMDB videos response:

1. **Filter by type:** Only consider videos where `type == "Trailer"`
2. **Prefer Spanish:** Prioritize videos where `iso_639_1 == "es"`
3. **Prefer official:** Among Spanish trailers, prefer `official == true`
4. **Fallback to English:** If no Spanish trailer, use English (`iso_639_1 == "en"`)
5. **Prefer highest quality:** Among matching trailers, prefer higher `size` (1080 > 720)
6. **Construct URL:** `https://www.youtube.com/watch?v={key}`

### 5. Implementation Location

Modify `Movie.create_from_tmdb()` to:
1. Accept a `TMDBService` instance as parameter (avoid creating new instance)
2. Fetch movie details with credits and videos
3. Extract and save all new fields
4. Handle API errors gracefully (log warning, continue with partial data)

### 6. API Call Efficiency

- Use `append_to_response=videos,credits` to fetch details, videos, and credits in a single API call
- Track API call with `APICallCounter.increment("tmdb")`

## Example Trailer Selection

```python
# TMDB videos response example
videos = [
    {"type": "Trailer", "iso_639_1": "es", "official": True, "key": "abc123", "size": 1080},
    {"type": "Trailer", "iso_639_1": "en", "official": True, "key": "def456", "size": 1080},
    {"type": "Teaser", "iso_639_1": "es", "official": True, "key": "ghi789", "size": 720},
]
# Should select: "abc123" (Spanish, official, trailer)
```

## Acceptance Criteria

- [ ] New movies have `trailer_url` populated when available
- [ ] Spanish trailers are preferred over English
- [ ] `duration_minutes` is populated from TMDB runtime
- [ ] `imdb_id` is populated from TMDB
- [ ] `director` field contains director name(s)
- [ ] `cast_summary` contains top billed actors
- [ ] Single API call fetches all needed data
- [ ] Existing tests continue to pass
- [ ] New tests cover trailer selection logic

## Migration Notes

- Add new nullable fields to avoid breaking existing data
- Consider backfill task for existing movies without details

## Dependencies

- `TMDBService.get_movie_details()` already supports `include_credits` parameter
- Need to add `include_videos` parameter to `get_movie_details()`
