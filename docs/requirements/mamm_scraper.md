# MAMM (elmamm.org) Scraper Requirements

## Purpose
Scrape movie showtimes and metadata from Museo de Arte Moderno de Medellín (MAMM) at https://www.elmamm.org/cine/#semana, and integrate with TMDB for movie matching and enrichment using the OOP `MovieLookupService` pattern.

## Source URLs
- **Weekly schedule page:** `https://www.elmamm.org/cine/#semana`
- **Individual movie pages:** `https://www.elmamm.org/producto/<movie-slug>/` (e.g., `/producto/un-poeta-2/`)

## Inputs
- Weekly showtimes HTML (snapshot: `movies_app/tasks/tests/html_snapshot/elmamm_org_semana`)
- Individual movie HTML (snapshot: `movies_app/tasks/tests/html_snapshot/elmamm_org_single_movie.html`)
- Live site URLs for production use

## Outputs
- Create or update `Movie` records with metadata and TMDB enrichment
- Create `Showtime` records for the single MAMM theater screen
- Store scraper-specific movie URLs in `MovieSourceUrl` table with `scraper_type=ScraperType.MAMM`

---

## HTML Structure Analysis

### Weekly Schedule Page (`#semana`)

The weekly schedule is rendered in a `<section class="schedule-week">` element containing a `<div class="row">` with one `<div class="col">` per day of the week.

**Structure per day:**
```html
<div class="col">                       <!-- or class="col past-day" for past dates -->
  <div class="day">
    <p class="small">viernes 23 Ene</p> <!-- Day name and date -->
  </div>
  <div class="card">
    <a href="https://www.elmamm.org/producto/perfect-blue-2/">
      <p class="small">2:00 pm</p>       <!-- Showtime -->
      <h3>Perfect Blue</h3>              <!-- Movie title -->
    </a>
    <span class="ciclo">Remasterizada en 4K</span>  <!-- Optional: special label -->
  </div>
  <!-- More cards... -->
</div>
```

**Key extraction points:**
| Element | Selector | Content |
|---------|----------|---------|
| Day/Date | `.col > .day > p.small` | e.g., "viernes 23 Ene" |
| Movie card | `.col > .card` | One per showtime |
| Movie URL | `.card > a[href]` | Full URL to movie detail page |
| Showtime | `.card > a > p.small` | e.g., "2:00 pm" |
| Movie title | `.card > a > h3` | Movie name |
| Special label | `.card > span.ciclo` | Optional (e.g., "Exclusivo Cine MAMM") |

**Notes:**
- Past days have class `past-day` and their `<a>` tags may lack `href` (no purchase link).
- Time format: "2:00 pm", "9:30 pm" (12-hour with am/pm, Spanish locale).
- Date format: "viernes 23 Ene" (weekday DD Mon, Spanish month abbreviations).
- Year is implied from current context (not explicit in HTML).

---

### Individual Movie Page (`/producto/<slug>/`)

Movie metadata is found in the product detail area.

**Key extraction points:**
| Data | Selector/Location | Example |
|------|-------------------|---------|
| Title | `h1.product_title` | "Un poeta" |
| Short description | `.woocommerce-product-details__short-description` | Contains age rating, duration, director, year, country, synopsis |
| Poster image | `.woocommerce-product-gallery__image img` | `src` attribute |
| YouTube trailer | `#tab-description iframe[src*="youtube"]` | Embedded video |
| Price | `p.price .woocommerce-Price-amount` | "$14.000" (all MAMM tickets are same price) |
| Showtimes (variants) | `select#fecha-y-hora option` | "21 ene, miércoles - 02:00 p.m" |

**Short description parsing:**
The `.woocommerce-product-details__short-description` contains:
```html
<p><strong>Mayores de 12 años | 120 min.</strong></p>
<p><strong>Director: </strong>Simón Mesa Soto</p>
<p>2025 | Colombia</p>
<p>La obsesión de Óscar Restrepo por la poesía...</p>
```

Parse to extract:
- **Age rating:** First `<p><strong>` text before `|` (e.g., "Mayores de 12 años")
- **Duration:** Number before "min" (e.g., 120)
- **Director:** Text after "Director:" (e.g., "Simón Mesa Soto")
- **Year:** 4-digit year in `<p>` (e.g., 2025)
- **Country:** Text after year and `|` (e.g., "Colombia")
- **Synopsis:** Remaining paragraph(s) with plot description

**og:description meta tag:**
Also available in the page `<head>`:
```html
<meta property="og:description" content="Mayores de 12 años | 120 min.  Director: Simón Mesa Soto  2025 | Colombia  La obsesión de Óscar Restrepo...">
```
This can be used as a fallback or for quick extraction.

---

## Architecture

### Files to Create
- `movies_app/tasks/mamm_download_task.py` — Celery task and core scraping logic
- `movies_app/management/commands/mamm_download.py` — Django management command wrapper
- `movies_app/tasks/tests/test_mamm_download_task.py` — Unit and integration tests

### Dependencies
- Use `MovieLookupService` from `movies_app.services.movie_lookup_service` for all movie creation/matching
- Use `MovieMetadata` and `TaskReport` dataclasses from `movies_app.tasks.download_utilities`
- Use `BeautifulSoup` with `lxml` parser for HTML parsing
- Use `camoufox` for headless browser scraping if dynamic content is required

---

## Scraping Logic

### Step 1: Scrape Weekly Schedule
1. Fetch HTML from `https://www.elmamm.org/cine/#semana` (or use snapshot for testing)
2. Find all `.schedule-week .col` elements
3. For each column (day):
   - Parse date from `.day > p.small` (e.g., "viernes 23 Ene" → `datetime.date`)
   - Skip if class contains `past-day` (optional: skip past showtimes)
   - For each `.card`:
     - Extract movie title from `h3`
     - Extract showtime from `p.small` (e.g., "2:00 pm" → `datetime.time`)
     - Extract movie URL from `a[href]` (may be missing for past showtimes)
     - Extract optional special label from `span.ciclo`

### Step 2: Scrape Movie Detail Pages
For each unique movie URL:
1. Fetch HTML from the movie detail page
2. Extract metadata:
   - Title: `h1.product_title`
   - Short description: `.woocommerce-product-details__short-description`
   - Parse age rating, duration, director, year, country, synopsis
   - Poster URL: `.woocommerce-product-gallery__image img[src]`
   - Trailer: `#tab-description iframe[src*="youtube"]`
3. Return a `MovieMetadata` object (or `None` on failure)

### Step 3: Create/Match Movies via MovieLookupService
1. Instantiate `MovieLookupService` with `TMDBService`, `storage_service`, and `source_name="mamm"`
2. For each movie:
   - Call `lookup_service.get_or_create_movie(movie_name, source_url, scraper_type=MovieSourceUrl.ScraperType.MAMM, metadata=metadata)`
   - If metadata scrape failed, proceed to TMDB lookup by name (do NOT skip)

### Step 4: Create Showtime Records
For each (movie, date, time) tuple:
1. Find or create the `Showtime` record
2. Associate with the MAMM `Theater` object
3. Store description (e.g., special label) if present

---

## Date/Time Parsing

### Date (from weekly schedule)
Format: `"viernes 23 Ene"` (weekday DD Mon)

Spanish day/month abbreviations:
| Spanish | English |
|---------|---------|
| lun/lunes | Monday |
| mar/martes | Tuesday |
| mié/miércoles | Wednesday |
| jue/jueves | Thursday |
| vie/viernes | Friday |
| sáb/sábado | Saturday |
| dom/domingo | Sunday |
| Ene | Jan |
| Feb | Feb |
| Mar | Mar |
| Abr | Apr |
| May | May |
| Jun | Jun |
| Jul | Jul |
| Ago | Aug |
| Sep | Sep |
| Oct | Oct |
| Nov | Nov |
| Dic | Dec |

**Parsing logic:**
1. Extract day number and month abbreviation using regex: `r"(\d{1,2})\s+(\w{3})"`
2. Map month abbreviation to month number
3. Infer year from current date (or next year if month < current month)

### Time (from weekly schedule)
Format: `"2:00 pm"` or `"9:30 pm"`

**Parsing logic:**
1. Use regex: `r"(\d{1,2}):(\d{2})\s*(am|pm)"`
2. Convert to 24-hour `datetime.time`

---

## Error Handling & Logging
- Log and skip movies or showtimes that cannot be parsed
- If metadata extraction fails, fall back to TMDB search by movie name only
- Record unfindable URLs using `lookup_service.record_unfindable_url()`
- Create `OperationalIssue` records for parse failures with severity `WARNING`
- Let exceptions propagate for unexpected errors (fail fast)

---

## Testing

### Test Files
- `movies_app/tasks/tests/html_snapshot/elmamm_org_semana` — Weekly schedule HTML
- `movies_app/tasks/tests/html_snapshot/elmamm_org_single_movie.html` — Single movie page HTML

### Test Cases
1. **Parse weekly schedule:** Extract all movies and showtimes from snapshot
2. **Parse single movie page:** Extract metadata from snapshot
3. **Date/time parsing:** Various formats and edge cases
4. **MovieLookupService integration:** Mock TMDB, verify movie creation
5. **Error handling:** Missing metadata, malformed HTML, unfindable movies

---

## Assumptions
- The canonical `Theater` object for MAMM exists in the DB before scraper runs (name: "MAMM", or similar)
- All showtimes are in `America/Bogota` timezone
- MAMM has a single screen (no screen/room distinction)
- Movie prices are uniform ($14,000 COP) and not stored per-showtime
- The `MovieSourceUrl` model stores scraper-specific URLs with `ScraperType` enum for deduplication across all scrapers
