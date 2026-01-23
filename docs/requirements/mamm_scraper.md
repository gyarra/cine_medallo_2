# MAMM (elmamm.org) Scraper Requirements

## Purpose
Scrape movie showtimes and metadata from Museo de Arte Moderno de Medellín (MAMM) at https://www.elmamm.org/cine/#semana, and integrate with TMDB for movie matching and enrichment using the OOP `MovieLookupService` pattern.

## Inputs
- Weekly showtimes HTML (snapshot: `movies_app/tasks/tests/html_snapshot/elmamm_org_semana`)
- Individual movie HTML (e.g., `movies_app/tasks/tests/html_snapshot/elmamm_org_single_movie.html`)
- Live site URLs for production use

## Outputs
- Create or update `Movie` records with metadata and TMDB enrichment
- Create `Showtime` records for the single MAMM screen
- Store theater-specific movie URLs in the new mapping table (if/when implemented)

## Architecture
- Implement as both a Django management command and a Celery task
- Use the OOP `MovieLookupService` for all movie creation/matching logic
- Scraper should be modular and reusable for future theaters

## Scraping Logic
- Parse the weekly showtimes page to extract:
  - Movie titles
  - Movie detail URLs
  - Showtimes (date, time)
- For each movie, parse the detail page to extract:
  - Genre, duration, director, synopsis, poster, etc.
- Normalize and store all showtimes for the single screen

## Error Handling & Logging
- Log and skip movies or showtimes that cannot be parsed
- If metadata extraction fails, fall back to TMDB search by movie name
- Record unfindable URLs using the OOP utility

## Testing
- Provide unit and integration tests using the provided HTML snapshots
- Ensure tests cover both successful and failure scenarios

## Assumptions
- The canonical Theater object for MAMM will exist in the DB before scraper runs
- The mapping table for theater-specific URLs will be used if/when available
