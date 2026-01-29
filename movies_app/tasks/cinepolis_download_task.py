"""
Cinepolis Scraper Task

Celery task for scraping movie showtime data from Cinepolis theaters in Colombia.

The home page is at: https://cinepolis.com.co/
Individual theater pages (cartelera) are at: https://cinepolis.com.co/cartelera/{city}/{theater-slug}

Movies are loaded at the chain level from the home page. Showtimes are scraped from
each theater's page, iterating through available dates using the #cmbFechas selector.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
import traceback
import unicodedata
from dataclasses import dataclass

from bs4 import BeautifulSoup
from camoufox.async_api import AsyncCamoufox

from config.celery_app import app
from movies_app.models import Movie, MovieSourceUrl, OperationalIssue, Theater
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.download_utilities import (
    BOGOTA_TZ,
    BROWSER_TIMEOUT_SECONDS,
    MovieMetadata,
    normalize_translation_type,
)
from movies_app.tasks.movie_and_showtime_saver_template import (
    MovieAndShowtimeSaverTemplate,
    MovieInfo,
    ShowtimeData,
    TaskReport,
)

logger = logging.getLogger(__name__)

SOURCE_NAME = "cinepolis"
TASK_NAME = "cinepolis_download_task"
CINEPOLIS_BASE_URL = "https://cinepolis.com.co"


@dataclass
class CinepolisMovieCard:
    title: str
    slug: str
    url: str
    poster_url: str


@dataclass
class CinepolisShowtime:
    date: datetime.date
    time: datetime.time
    format: str
    translation_type: str


class CinepolisScraperAndHTMLParser:
    """Stateless class for fetching and parsing Cinepolis web pages."""

    @staticmethod
    async def _fetch_cinepolis_page_async(
        url: str,
        wait_selector: str,
    ) -> str:
        """Fetch a Cinepolis page using browser automation."""
        logger.info(f"Scraping Cinepolis page: {url}")

        async with AsyncCamoufox(headless=True) as browser:
            context = await browser.new_context(ignore_https_errors=True)  # pyright: ignore[reportAttributeAccessIssue]
            page = await context.new_page()

            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )

                await page.wait_for_selector(
                    wait_selector,
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )

                await asyncio.sleep(2)

                html_content: str = await page.content()
            finally:
                await context.close()

        return html_content

    @staticmethod
    def download_home_page_html() -> str:
        """Download the home page HTML to get the list of movies."""
        return asyncio.run(
            CinepolisScraperAndHTMLParser._fetch_cinepolis_page_async(
                CINEPOLIS_BASE_URL,
                wait_selector=".listCartelera",
            )
        )

    @staticmethod
    async def _fetch_movies_from_all_cities_async() -> list[str]:
        """Fetch movie listings from all cities by iterating through the city dropdown."""
        logger.info("Scraping Cinepolis movies from all cities")
        all_html_pages: list[str] = []

        async with AsyncCamoufox(headless=True) as browser:
            context = await browser.new_context(ignore_https_errors=True)  # pyright: ignore[reportAttributeAccessIssue]
            page = await context.new_page()

            try:
                await page.goto(
                    CINEPOLIS_BASE_URL,
                    wait_until="domcontentloaded",
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )

                await page.wait_for_selector(
                    ".listCartelera",
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )

                await asyncio.sleep(2)

                # Get city options from dropdown
                city_options = await page.query_selector_all("#cmbCiudadesCartelera option")
                city_values: list[str] = []
                for option in city_options:
                    value = await option.get_attribute("value")
                    # Skip the placeholder option
                    if value and value != "Selecciona una ciudad":
                        city_values.append(value)

                logger.info(f"Found {len(city_values)} cities to scrape")

                # Get HTML for the first city (already loaded)
                if city_values:
                    html_content: str = await page.content()
                    all_html_pages.append(html_content)
                    logger.info("Collected movies from first city")

                # Iterate through remaining cities
                for city_value in city_values[1:]:
                    try:
                        await page.select_option("#cmbCiudadesCartelera", value=city_value)
                        await asyncio.sleep(2)

                        # Wait for content to update
                        await page.wait_for_selector(
                            ".listCartelera",
                            timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                        )

                        html_content = await page.content()
                        all_html_pages.append(html_content)
                        logger.info(f"Collected movies from city index {city_value}")
                    except Exception as e:
                        logger.warning(f"Failed to get movies for city {city_value}: {e}")
            finally:
                await context.close()

        return all_html_pages

    @staticmethod
    def download_movies_from_all_cities() -> list[str]:
        """Download movie listings from all cities."""
        return asyncio.run(
            CinepolisScraperAndHTMLParser._fetch_movies_from_all_cities_async()
        )

    @staticmethod
    def download_theater_page_html(url: str) -> str:
        """Download theater page HTML to get showtimes."""
        return asyncio.run(
            CinepolisScraperAndHTMLParser._fetch_cinepolis_page_async(
                url,
                wait_selector=".listaCarteleraHorario",
            )
        )

    @staticmethod
    async def _fetch_theater_page_with_dates_async(url: str) -> dict[str, str]:
        """Fetch theater page HTML for all available dates."""
        logger.info(f"Scraping Cinepolis theater page with date iteration: {url}")
        pages_by_date: dict[str, str] = {}

        async with AsyncCamoufox(headless=True) as browser:
            context = await browser.new_context(ignore_https_errors=True)  # pyright: ignore[reportAttributeAccessIssue]
            page = await context.new_page()

            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )

                await page.wait_for_selector(
                    ".listaCarteleraHorario",
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )

                await asyncio.sleep(2)

                # Get available dates from the dropdown
                date_options = await page.query_selector_all("#cmbFechas option")
                date_values: list[str] = []
                for option in date_options:
                    value = await option.get_attribute("value")
                    if value:
                        date_values.append(value)

                logger.info(f"Found {len(date_values)} dates: {date_values}")

                # Get HTML for first date (already loaded)
                if date_values:
                    first_date = date_values[0]
                    html_content: str = await page.content()
                    pages_by_date[first_date] = html_content

                # Iterate through remaining dates
                for date_value in date_values[1:]:
                    try:
                        await page.select_option("#cmbFechas", value=date_value)
                        await asyncio.sleep(2)

                        # Wait for content to update
                        await page.wait_for_selector(
                            ".listaCarteleraHorario",
                            timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                        )

                        html_content = await page.content()
                        pages_by_date[date_value] = html_content
                        logger.info(f"Collected showtimes for date: {date_value}")
                    except Exception as e:
                        logger.warning(f"Failed to get showtimes for date {date_value}: {e}")
            finally:
                await context.close()

        return pages_by_date

    @staticmethod
    def download_theater_pages_for_all_dates(url: str) -> dict[str, str]:
        """Download theater page HTML for all available dates."""
        return asyncio.run(
            CinepolisScraperAndHTMLParser._fetch_theater_page_with_dates_async(url)
        )

    @staticmethod
    def parse_movies_from_home_page_html(html_content: str) -> list[CinepolisMovieCard]:
        """Parse movies from the home page."""
        soup = BeautifulSoup(html_content, "lxml")
        movies: list[CinepolisMovieCard] = []
        seen_slugs: set[str] = set()

        cartelera_list = soup.find("ul", class_="listCartelera")
        if not cartelera_list:
            logger.warning("Could not find cartelera list on home page")
            return movies

        movie_items = cartelera_list.find_all("li", recursive=False)

        for item in movie_items:
            cartelera_link = item.find("a", class_="lnkCartelera")
            if not cartelera_link:
                continue

            slug_attr = cartelera_link.get("data-id")
            if not slug_attr:
                continue
            slug = str(slug_attr)
            if slug in seen_slugs:
                continue
            seen_slugs.add(slug)

            # Get title from h1 inside the item
            title_elem = item.find("h1")
            if title_elem:
                title = title_elem.get_text(strip=True)
            else:
                title = slug.replace("-", " ").title()

            # Get poster URL
            img_elem = item.find("img")
            poster_url = ""
            if img_elem:
                poster_url = str(img_elem.get("src", ""))

            movie_url = f"{CINEPOLIS_BASE_URL}/pelicula/{slug}"

            movies.append(CinepolisMovieCard(
                title=title,
                slug=slug,
                url=movie_url,
                poster_url=poster_url,
            ))

        return movies

    @staticmethod
    def parse_date_from_text(date_text: str) -> datetime.date | None:
        """Parse date text like '27 enero' or 'Hoy (27 enero)'."""
        # Extract date from format like "27 enero" or "Hoy (27 enero)" or "Mañana (28 enero)"
        match = re.search(r"(\d{1,2})\s+(\w+)", date_text)
        if not match:
            return None

        day = int(match.group(1))
        month_name = match.group(2).lower()

        spanish_months = {
            "enero": 1,
            "febrero": 2,
            "marzo": 3,
            "abril": 4,
            "mayo": 5,
            "junio": 6,
            "julio": 7,
            "agosto": 8,
            "septiembre": 9,
            "octubre": 10,
            "noviembre": 11,
            "diciembre": 12,
        }

        month = spanish_months.get(month_name)
        if not month:
            return None

        today = datetime.datetime.now(BOGOTA_TZ).date()
        year = today.year

        try:
            parsed_date = datetime.date(year, month, day)
            # Handle year boundary
            delta = (parsed_date - today).days
            if delta > 180:
                parsed_date = parsed_date.replace(year=year - 1)
            elif delta < -180:
                parsed_date = parsed_date.replace(year=year + 1)
            return parsed_date
        except ValueError:
            return None

    @staticmethod
    def parse_showtimes_from_theater_html(
        html_content: str,
        date_text: str,
    ) -> list[tuple[str, CinepolisShowtime]]:
        """Parse showtimes from theater page HTML.

        Returns a list of tuples (movie_title, showtime).
        """
        soup = BeautifulSoup(html_content, "lxml")
        results: list[tuple[str, CinepolisShowtime]] = []

        parsed_date = CinepolisScraperAndHTMLParser.parse_date_from_text(date_text)
        if not parsed_date:
            logger.warning(f"Could not parse date from: {date_text}")
            return results

        # Find all movie articles
        movie_articles = soup.find_all("article", class_="tituloPelicula")

        for article in movie_articles:
            # Get movie title
            title_link = article.find("a", class_="datalayer-movie")
            if not title_link:
                continue

            movie_title = title_link.get_text(strip=True)
            if not movie_title:
                continue

            # Find all format sections (horarioExp divs)
            format_sections = article.find_all("div", class_="horarioExp")

            for format_section in format_sections:
                # Parse format and translation type from class
                classes_attr = format_section.get("class")
                classes: list[str] = list(classes_attr) if classes_attr else []
                format_str = ""
                translation_type = ""

                for cls in classes:
                    upper_cls = str(cls).upper()
                    if upper_cls in ("2D", "3D", "4DX", "IMAX", "DIG"):
                        format_str = upper_cls
                    elif upper_cls in ("DOB", "SUB"):
                        translation_type = upper_cls

                # Also check the format text inside col3
                format_col = format_section.find("div", class_="col3")
                if format_col:
                    format_text = format_col.get_text(strip=True).upper()
                    if "DOB" in format_text:
                        translation_type = "DOB"
                    elif "SUB" in format_text:
                        translation_type = "SUB"
                    if "2D" in format_text:
                        format_str = "2D"
                    elif "3D" in format_text:
                        format_str = "3D"
                    elif "4DX" in format_text:
                        format_str = "4DX"
                    elif "IMAX" in format_text:
                        format_str = "IMAX"
                    elif "DIG" in format_text and not format_str:
                        format_str = "DIG"

                # Find all showtime buttons
                time_buttons = format_section.find_all("time", class_="btnhorario")

                for time_button in time_buttons:
                    time_text = time_button.get_text(strip=True)
                    if not time_text:
                        continue

                    parsed_time = CinepolisScraperAndHTMLParser._parse_time(time_text)
                    if not parsed_time:
                        logger.warning(f"Could not parse time: {time_text}")
                        continue

                    results.append((movie_title, CinepolisShowtime(
                        date=parsed_date,
                        time=parsed_time,
                        format=format_str,
                        translation_type=translation_type,
                    )))

        return results

    @staticmethod
    def _parse_time(time_text: str) -> datetime.time | None:
        """Parse time text like '17:00' or '14:40'."""
        time_text = time_text.strip()
        match = re.match(r"(\d{1,2}):(\d{2})", time_text)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            try:
                return datetime.time(hour, minute)
            except ValueError:
                return None
        return None


class CinepolisShowtimeSaver(MovieAndShowtimeSaverTemplate):
    """Scraper implementation for Cinepolis theaters."""

    def __init__(
        self,
        scraper: CinepolisScraperAndHTMLParser,
        tmdb_service: TMDBService,
        storage_service: SupabaseStorageService | None,
    ):
        super().__init__(
            tmdb_service=tmdb_service,
            storage_service=storage_service,
            source_name=SOURCE_NAME,
            scraper_type="cinepolis",
            scraper_type_enum=MovieSourceUrl.ScraperType.CINEPOLIS,
            task_name=TASK_NAME,
        )
        self.scraper = scraper

    def _find_movies_for_chain(self) -> list[MovieInfo]:
        """Find all movies from all cities on the Cinepolis home page."""
        html_pages = self.scraper.download_movies_from_all_cities()

        # Collect movies from all city pages and deduplicate by slug
        seen_slugs: set[str] = set()
        all_movies: list[MovieInfo] = []

        for html in html_pages:
            movie_cards = self.scraper.parse_movies_from_home_page_html(html)
            for card in movie_cards:
                if card.slug not in seen_slugs:
                    seen_slugs.add(card.slug)
                    all_movies.append(MovieInfo(name=card.title, source_url=card.url))

        logger.info(f"Found {len(all_movies)} unique movies across all Cinepolis cities")

        return all_movies

    def _find_movies(self, theater: Theater) -> list[MovieInfo]:
        """Not used - movies are loaded at chain level via _find_movies_for_chain."""
        return []

    def _get_movie_metadata(self, movie_info: MovieInfo) -> MovieMetadata | None:
        """Return None - TMDB service will be used for metadata."""
        return None

    def _process_theater(
        self,
        theater: Theater,
        movies_cache: dict[str, Movie | None],
    ) -> int:
        """
        Override to process theater with date iteration.

        Goes to theater page, collects showtimes for all dates using #cmbFechas widget.
        """
        if not theater.download_source_url:
            logger.warning(f"No download_source_url for theater {theater.name}")
            return 0

        try:
            pages_by_date = self.scraper.download_theater_pages_for_all_dates(
                theater.download_source_url
            )
        except Exception as e:
            logger.error(f"Failed to download theater pages for {theater.name}: {e}")
            OperationalIssue.objects.create(
                name="Cinepolis Theater Download Failed",
                task=TASK_NAME,
                error_message=str(e),
                traceback=traceback.format_exc(),
                context={"theater_name": theater.name, "url": theater.download_source_url},
                severity=OperationalIssue.Severity.ERROR,
            )
            return 0

        all_showtimes: list[ShowtimeData] = []

        for date_text, html_content in pages_by_date.items():
            showtimes_with_titles = self.scraper.parse_showtimes_from_theater_html(
                html_content, date_text
            )

            for movie_title, showtime in showtimes_with_titles:
                # Find movie in cache by title
                movie = self._find_movie_in_cache_by_title(movie_title, movies_cache)
                if not movie:
                    logger.debug(f"Movie not found in cache: {movie_title}")
                    continue

                translation_type = normalize_translation_type(
                    showtime.translation_type,
                    task=TASK_NAME,
                    context={"theater": theater.name, "movie": movie_title},
                )

                all_showtimes.append(ShowtimeData(
                    movie=movie,
                    date=showtime.date,
                    time=showtime.time,
                    format=showtime.format,
                    translation_type=translation_type,
                    screen="",
                    source_url=f"{CINEPOLIS_BASE_URL}/pelicula/{movie_title.lower().replace(' ', '-')}",
                ))

        return self._save_showtimes_for_theater(theater, all_showtimes)

    @staticmethod
    def _generate_slug_from_title(title: str) -> str:
        """Generate a URL slug from a movie title."""
        # Normalize unicode and convert to lowercase
        slug = title.lower().strip()
        # Remove accents
        slug = unicodedata.normalize("NFKD", slug)
        slug = "".join(c for c in slug if not unicodedata.combining(c))
        # Replace spaces with hyphens
        slug = slug.replace(" ", "-")
        # Remove special characters except hyphens
        slug = re.sub(r"[^a-z0-9-]", "", slug)
        # Remove consecutive hyphens
        slug = re.sub(r"-+", "-", slug)
        # Remove leading/trailing hyphens
        slug = slug.strip("-")
        return slug

    def _find_movie_in_cache_by_title(
        self,
        title: str,
        movies_cache: dict[str, Movie | None],
    ) -> Movie | None:
        """Find a movie in the cache by matching title or URL."""
        title_lower = title.lower().strip()

        # First, try to match by URL (most reliable)
        # Generate the expected URL from the title using proper slug generation
        slug = self._generate_slug_from_title(title)
        expected_url = f"{CINEPOLIS_BASE_URL}/pelicula/{slug}"
        if expected_url in movies_cache:
            return movies_cache[expected_url]

        # Fall back to title matching
        for _, movie in movies_cache.items():
            if movie is None:
                continue

            # Check movie's Spanish title
            if movie.title_es and movie.title_es.lower().strip() == title_lower:
                return movie

            # Check movie's original title
            if movie.original_title and movie.original_title.lower().strip() == title_lower:
                return movie

        return None

    def _process_showtimes_for_theater(
        self,
        theater: Theater,
        movies_for_theater: list[MovieInfo],
        movies_cache: dict[str, Movie | None],
    ) -> int:
        """Not used - overridden _process_theater handles everything."""
        return 0


@app.task
def cinepolis_download_task() -> TaskReport:
    """Celery task to download Cinepolis showtimes."""
    scraper = CinepolisScraperAndHTMLParser()
    tmdb_service = TMDBService()
    storage_service = SupabaseStorageService.create_from_settings()

    saver = CinepolisShowtimeSaver(scraper, tmdb_service, storage_service)
    report = saver.execute()
    report.print_report()
    return report
