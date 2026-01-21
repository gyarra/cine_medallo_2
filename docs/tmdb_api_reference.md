# TMDB API Reference

Documentation for The Movie Database (TMDB) API fields used in this project.

## Trailer URLs

TMDB provides trailers via the **Videos endpoint** (`/movie/{movie_id}/videos`), not in the main Details response. Options:
1. Make a separate API call to `/movie/{movie_id}/videos`
2. Use `append_to_response=videos` on the details endpoint

### Video Response Fields

| Field | Type | Description |
|-------|------|-------------|
| `key` | string | YouTube video ID (e.g., `"O-b2VfmmbyA"`) |
| `site` | string | Platform (usually `"YouTube"`) |
| `type` | string | `"Trailer"`, `"Teaser"`, `"Clip"`, `"Featurette"`, etc. |
| `official` | bool | Official vs fan uploads |
| `name` | string | Video title |
| `size` | int | Video resolution (720, 1080, etc.) |
| `published_at` | string | ISO 8601 timestamp |
| `id` | string | TMDB video ID |
| `iso_639_1` | string | Language code |
| `iso_3166_1` | string | Country code |

To construct a trailer URL: `https://www.youtube.com/watch?v={key}`

---

## Movie Details Fields

Endpoint: `GET /movie/{movie_id}`

### Basic Details

| Field | Type | Description |
|-------|------|-------------|
| `id` | int | TMDB ID |
| `title` | string | Localized title |
| `original_title` | string | Original language title |
| `overview` | string | Plot summary |
| `tagline` | string | Marketing tagline |
| `release_date` | string | `YYYY-MM-DD` format |
| `runtime` | int | Minutes |
| `budget` | int | USD |
| `revenue` | int | USD |
| `status` | string | `Released`, `Post Production`, etc. |
| `adult` | bool | Adult content flag |
| `video` | bool | Has video content |
| `popularity` | float | TMDB popularity score |
| `vote_average` | float | 0-10 rating |
| `vote_count` | int | Number of votes |
| `poster_path` | string | Poster image path |
| `backdrop_path` | string | Background image path |
| `homepage` | string | Official website |
| `imdb_id` | string | IMDb ID (e.g., `tt0137523`) |
| `original_language` | string | ISO 639-1 code |

### Nested Objects

| Field | Type | Description |
|-------|------|-------------|
| `genres` | array | `[{id, name}]` |
| `production_companies` | array | `[{id, name, logo_path, origin_country}]` |
| `production_countries` | array | `[{iso_3166_1, name}]` |
| `spoken_languages` | array | `[{english_name, iso_639_1, name}]` |
| `belongs_to_collection` | object | Collection info if part of franchise |

---

## Additional Endpoints

Available via `append_to_response` parameter (comma-separated, max 20):

| Endpoint | Data |
|----------|------|
| `credits` | Cast & crew |
| `videos` | Trailers, teasers, clips |
| `images` | Posters, backdrops, logos |
| `keywords` | Content keywords |
| `release_dates` | Regional release dates & certifications |
| `external_ids` | IMDb, Facebook, Twitter, Instagram IDs |
| `watch/providers` | Streaming availability by region |
| `recommendations` | Similar movies |
| `reviews` | User reviews |
| `translations` | Available translations |

### Example Request

```
GET /movie/550?append_to_response=credits,videos&language=es-ES
```

---

## Image URLs

Image paths returned by the API are partial. To construct full URLs:

```
https://image.tmdb.org/t/p/{size}{path}
```

Poster sizes: `w92`, `w154`, `w185`, `w342`, `w500`, `w780`, `original`
Backdrop sizes: `w300`, `w780`, `w1280`, `original`

Example: `https://image.tmdb.org/t/p/w500/pB8BM7pdSp6B6Ih7QZ4DrQ3PmJK.jpg`

---

## Credits Response

When using `append_to_response=credits`:

### Cast
| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Person TMDB ID |
| `name` | string | Actor name |
| `character` | string | Character played |
| `order` | int | Billing order |
| `profile_path` | string | Profile image path |

### Crew
| Field | Type | Description |
|-------|------|-------------|
| `id` | int | Person TMDB ID |
| `name` | string | Crew member name |
| `job` | string | Role (e.g., `"Director"`) |
| `department` | string | Department (e.g., `"Directing"`) |
| `profile_path` | string | Profile image path |
