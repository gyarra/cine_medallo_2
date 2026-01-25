# Cineprox Scraper Requirements

## Overview

Scraper for **Cineprox** (formerly Procinal) theaters. Cineprox is a React-based single-page application (SPA) that renders movie listings and showtimes client-side.

**Source website:** https://www.cineprox.com

## Theaters Using This Scraper

From `seed_data/theaters.json`:
- **Procinal - Parque Fabricato** (Bello): `https://www.cineprox.com/cartelera/bello/parque-fabricato`
- **Procinal - Puerta del Norte** (Bello): `https://www.cineprox.com/cartelera/bello/puerta-del-norte`

## URL Patterns

### Cartelera (Movie List) Page
```
https://www.cineprox.com/cartelera/{city}/{theater_slug}
```
Example: `https://www.cineprox.com/cartelera/bello/parque-fabricato`

### Movie Detail Page
```
https://www.cineprox.com/detalle-pelicula/{movie_id}-{movie_slug}?idCiudad={city_id}&idTeatro={theater_id}
```
Example: `https://www.cineprox.com/detalle-pelicula/2005-sin-piedad?idCiudad=30&idTeatro=328`

**Important URL handling:**
- `source_url` for Showtime records: INCLUDE the ID params (`?idCiudad=X&idTeatro=Y`)
- `movie_source_url` for MovieSourceUrl records: DO NOT include ID params (just the base URL)

## HTML Structure Analysis

### Cartelera Page (Movie List)

Movie cards are found in `div#grid` inside `section.Cinema`:

```html
<div class="col-md-3 element-item estrenos" data-testid="movie-card-2005" style="cursor: pointer;">
    <div class="card movie-card">
        <div class="card-header estrenos">Estrenos</div>
        <div class="image-container">
            <img src="https://www.pantallascineprox.com/img/peliculas/2005.jpg?v=1.0.36"
                 class="card-img-top"
                 alt="SIN PIEDAD">
        </div>
        <div class="card-body">
            <p class="card-text">SIN PIEDAD</p>
        </div>
    </div>
</div>
```

**Key data extraction from cartelera:**
- Movie ID: Extract from `data-testid` attribute (e.g., `movie-card-2005` → ID is `2005`)
- Movie title: `.card-text` text content
- Poster URL: `.card-img-top` `src` attribute
- Movie category: `.card-header` class and text (`preventa`, `estrenos`, `cartelera`, `pronto`)

**No href links:** Movie cards do not have `<a>` tags—clicks are handled by JavaScript/React using the movie ID.

### Movie Detail Page (Showtime Information)

Movie metadata is found in `section.pelicula`:

```html
<section class="pelicula">
    <div class="card movie-component-card">
        <div class="text-center card-header Estrenos">Estrenos</div>
        <img src="https://www.pantallascineprox.com/img/peliculas/2005.jpg?v=1.0.36"
             class="card-img-top" alt="SIN PIEDAD">
    </div>
    <div class="InfoPelicula">
        <h2>SIN PIEDAD</h2>
        <h5><span>Nombre original:</span> MERCY</h5>
        <h6><span>Sinopsis: </span></h6>
        <p>En un futuro cercano, el detective Chris Raven...</p>
    </div>
    <div class="Info1Peli">
        <h3>Información</h3>
        <ul>
            <li><span>Clasificación: </span>12 Años</li>
            <li><span>Duración: </span>100 Minutos</li>
            <li><span>Género: </span>Acción</li>
            <li><span>Estreno: </span>22/enero/2026</li>
            <li><span>País: </span>ESTADOS UNIDOS</li>
            <li><span>Director: </span>Timur Bekmambetov</li>
            <li><span>Reparto: </span>Chris Pratt - Rebecca Ferguson - ...</li>
        </ul>
    </div>
</section>
```

### Showtime Information

Date selector in `section.infoSalasFech`:

```html
<div class="calendar-container">
    <div id="day-0" class="day-item selected">
        <span class="day">SÁB</span>
        <span class="date">24 ene</span>
    </div>
    <div id="day-1" class="day-item">
        <span class="day">DOM</span>
        <span class="date">25 ene</span>
    </div>
    <!-- More days... -->
</div>
```

Theater accordions with showtimes:

```html
<div class="accordion-item">
    <h2 class="accordion-header">
        <button class="accordion-button">Parque Fabricato - Bello</button>
    </h2>
    <div class="accordion-collapse collapse show">
        <div class="tab-pane fade show active" id="pills-todas">
            <h5 class="tipoSala"><b>General</b></h5>
            <div class="row g-1">
                <div class="col-sm-6 col-md-4 col-lg-2">
                    <div class="movie-schedule-header text-center">
                        <span style="font-weight: bold;">2D</span> - DOB
                    </div>
                    <div class="movie-schedule-card">
                        <div class="movie-schedule-time">4:25 pm</div>
                        <div class="movie-schedule-price">$ 21.900</div>
                        <div class="buy-button disabled">Finalizado</div>
                    </div>
                </div>
                <!-- More showtimes... -->
            </div>
        </div>
    </div>
</div>
```

**Key showtime data:**
- Room type: `.tipoSala b` (e.g., "General")
- Format: `.movie-schedule-header` (e.g., "2D - DOB" for 2D Dubbed)
- Time: `.movie-schedule-time` (e.g., "4:25 pm")
- Price: `.movie-schedule-price` (e.g., "$ 21.900")
- Theater name: `.accordion-button` text (e.g., "Parque Fabricato - Bello")

## Data Extraction Requirements

### From Cartelera Page
1. Extract all movie IDs and titles
2. Skip movies with category "pronto" (coming soon)
3. Generate movie detail URLs for each movie

### From Movie Detail Page
1. **Movie metadata:**
   - Title (from `h2` in `.InfoPelicula`)
   - Original title (from `h5` with "Nombre original:")
   - Synopsis (from `p` after "Sinopsis:")
   - Classification/age rating (e.g., "12 Años")
   - Duration in minutes (parse "100 Minutos")
   - Genre
   - Release date (parse "22/enero/2026")
   - Country
   - Director
   - Cast (actors)

2. **Showtimes:**
   - Parse all available dates from calendar
   - For each date, extract showtimes from the theater accordion
   - Parse time (convert "4:25 pm" to 24-hour format)
   - Parse format (2D/3D, DOB/SUB)
   - Parse room type (General, etc.)

## Architecture

Follow MAMM scraper two-class pattern:

### CineproxScraperAndHTMLParser (Stateless)
- `download_cartelera_html(url: str) -> str`
- `download_movie_detail_html(url: str) -> str`
- `parse_movies_from_cartelera_html(html: str) -> list[CineproxMovieCard]`
- `parse_movie_metadata_from_detail_html(html: str) -> CineproxMovieMetadata | None`
- `parse_showtimes_from_detail_html(html: str, date: datetime.date, theater_name: str) -> list[CineproxShowtime]`
- `generate_movie_detail_url(movie_id: str, slug: str, city_id: str | None, theater_id: str | None) -> str`
- `generate_movie_source_url(movie_id: str, slug: str) -> str` (without query params)

### CineproxShowtimeSaver (Stateful Coordinator)
- Inject `CineproxScraperAndHTMLParser`, `TMDBService`, `SupabaseStorageService`
- Iterate through theaters with `scraper_type="cineprox"`
- Process movies and save to database using `MovieLookupService`
- Save showtimes using `@transaction.atomic` per date

## Dataclasses

```python
@dataclass
class CineproxMovieCard:
    movie_id: str          # e.g., "2005"
    title: str             # e.g., "SIN PIEDAD"
    slug: str              # Generated from title (e.g., "sin-piedad")
    poster_url: str
    category: str          # "preventa", "estrenos", "cartelera", "pronto"

@dataclass
class CineproxMovieMetadata:
    title: str
    original_title: str | None
    synopsis: str
    classification: str     # e.g., "12 Años"
    duration_minutes: int | None
    genre: str
    release_date: datetime.date | None
    country: str
    director: str
    actors: list[str]
    poster_url: str

@dataclass
class CineproxShowtime:
    date: datetime.date
    time: datetime.time
    format: str             # e.g., "2D"
    language: str           # e.g., "DOB" or "SUB"
    room_type: str          # e.g., "General"
    price: str | None       # e.g., "$ 21.900"
```

## Theater Configuration

City and theater IDs are stored in `Theater.scraper_config` JSONField:

```json
{
  "scraper_config": {"city_id": "30", "theater_id": "328"}
}
```

These IDs are required to generate movie detail URLs with the correct theater context.

## Special Considerations

1. **React SPA:** The site is JavaScript-rendered. HTML snapshots were captured after JavaScript execution.

2. **Theater matching:** The accordion headers include city (e.g., "Parque Fabricato - Bello"). Match against our database by theater name.

3. **Date parsing:** Calendar dates like "24 ene" need year inference (use reference year with wrap-around logic like MAMM).

4. **Time parsing:** Format is "4:25 pm" - convert to 24-hour time.

5. **Movie URL handling:**
   - For MovieSourceUrl: `https://www.cineprox.com/detalle-pelicula/2005-sin-piedad`
   - For Showtime.source_url: `https://www.cineprox.com/detalle-pelicula/2005-sin-piedad?idCiudad=30&idTeatro=328`

6. **Filter "pronto" movies:** Skip movies with category "pronto" (coming soon).

7. **ScraperType:** Use existing `MovieSourceUrl.ScraperType.CINEPROX`.

## Validation & Error Handling

Create `OperationalIssue` records for all unexpected conditions:

### Required Validations

1. **Theater accordion expanded check:**
   - On the movie detail page, verify the accordion for our target theater has class `show` (expanded)
   - If the accordion is collapsed, the `?idTeatro=X` param may be wrong
   - Create `OperationalIssue` with severity `WARNING`:
     ```python
     OperationalIssue.objects.create(
         name="Cineprox Theater Accordion Not Expanded",
         task="cineprox_download_task",
         error_message=f"Theater accordion not expanded for {theater_name}. Check if theater_id is correct.",
         context={"theater_name": theater_name, "theater_id": theater_id, "movie_url": url},
         severity=OperationalIssue.Severity.WARNING,
     )
     ```

2. **Missing scraper_config:**
   - If a theater has `scraper_type="cineprox"` but no `scraper_config`, skip and log error
   - Create `OperationalIssue` with severity `ERROR`

3. **HTML parsing failures:**
   - If cartelera page has no movie cards, create `OperationalIssue`
   - If movie detail page structure is unexpected, create `OperationalIssue`

4. **Network/HTTP errors:**
   - Log failed downloads with URL and status code
   - Create `OperationalIssue` for each failure

5. **Date/time parsing errors:**
   - Log unparseable dates/times with the raw string
   - Create `OperationalIssue` but continue processing other showtimes

6. **No showtimes found:**
   - If a movie detail page has no showtimes for the target theater, log but don't create issue (may be normal)

### OperationalIssue Severity Guidelines

- `ERROR`: Scraper cannot continue (missing config, HTTP 500, etc.)
- `WARNING`: Scraper can continue but data may be incomplete (accordion not expanded, parse failures)
- `INFO`: Informational (e.g., movie not found in TMDB)

## Files to Create

1. `movies_app/tasks/cineprox_download_task.py` - Main scraper implementation
2. `movies_app/tasks/tests/test_cineprox_download_task.py` - Unit tests
3. `movies_app/management/commands/cineprox_download.py` - Management command (runs task for all theaters)
4. `movies_app/management/commands/cineprox_download_for_one_theater.py` - Management command (runs for single theater)

### Management Command: cineprox_download.py

Simple wrapper that runs the Celery task for all Cineprox theaters:

```bash
python manage.py cineprox_download
```

### Management Command: cineprox_download_for_one_theater.py

Runs the scraper for a single theater. Useful for testing and debugging.

```bash
# List available Cineprox theaters
python manage.py cineprox_download_for_one_theater --list

# Scrape showtimes for one theater
python manage.py cineprox_download_for_one_theater procinal-parque-fabricato-bello
```

## Testing Requirements

- Unit tests using HTML snapshots (already exist in `html_snapshot/`)
- Test cartelera parsing
- Test movie detail parsing
- Test showtime extraction
- Test URL generation methods
- Integration test with real scraper classes
