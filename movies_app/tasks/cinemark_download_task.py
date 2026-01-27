"""
Cinemark Scraper Task

Celery task for scraping movie showtime data from Cinemark theaters.

Theater pages are at: https://www.cinemark.com.co/ciudad/{city}/{theater_slug}
Movie detail pages are at: https://www.cinemark.com.co/cartelera/{city}/{movie_slug}

The theater page (cartelera) displays:
- A week selector (.week) with clickable day buttons
- Movie sections (.section-detail) showing title, URL, and showtimes for each day

This scraper:
1. Loads the theater page
2. Clicks through each day in the week selector
3. Extracts movies and their showtimes for each day
4. Collects all unique movies across all days
"""

from __future__ import annotations

import asyncio
import datetime
import logging
import re
import traceback
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, Tag
from camoufox.async_api import AsyncCamoufox

from config.celery_app import app
from movies_app.models import Movie, MovieSourceUrl, OperationalIssue, Theater
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.download_utilities import (
    BROWSER_TIMEOUT_SECONDS,
    MovieMetadata,
    normalize_translation_type,
    parse_time_string,
)
from movies_app.tasks.movie_and_showtime_saver_template import (
    MovieAndShowtimeSaverTemplate,
    MovieInfo,
    ShowtimeData,
)

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)

SOURCE_NAME = "cinemark"
TASK_NAME = "cinemark_download_task"

SPANISH_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4,
    "may": 5, "jun": 6, "jul": 7, "ago": 8,
    "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


@dataclass
class CinemarkMovieCard:
    """Movie info extracted from cartelera listing."""
    title: str
    slug: str
    url: str


@dataclass
class CinemarkShowtimeBlock:
    """A block of showtimes with shared format/translation/seat info."""
    format: str
    translation_type: str
    seat_type: str
    times: list[datetime.time] = field(default_factory=list)


@dataclass
class CinemarkMovieWithShowtimes:
    """Movie data with showtimes for a specific date."""
    title: str
    url: str
    date: datetime.date
    showtime_blocks: list[CinemarkShowtimeBlock] = field(default_factory=list)


class CinemarkScraperAndHTMLParser:
    """
    Scraper that uses Playwright to interact with Cinemark pages.

    The Cinemark cartelera page is a React SPA that requires JavaScript interaction:
    - Movies are displayed in .section-detail divs within .list-movies > .d-block
    - A week selector (.week) allows clicking different days to update the movie list
    - Showtimes are displayed inline within each .section-detail
    """

    @staticmethod
    def scrape_theater_movies_and_showtimes(url: str) -> list[CinemarkMovieWithShowtimes]:
        """
        Scrape all movies and showtimes from theater cartelera page.

        Clicks through each day in the week selector to collect all movies and showtimes.
        """
        return asyncio.run(CinemarkScraperAndHTMLParser._scrape_theater_async(url))

    @staticmethod
    async def _dismiss_modals(page: Page) -> None:
        """Dismiss any modal dialogs that might block interactions (cookie consent, promos, etc.)."""
        # Try to close Ant Design modals by clicking close button or outside
        modal_close_selectors = [
            ".ant-modal-close",
            ".ant-modal-wrap .ant-btn-primary",
            "button[aria-label='Close']",
            ".ant-modal-wrap button:has-text('Aceptar')",
            ".ant-modal-wrap button:has-text('Cerrar')",
            ".ant-modal-wrap button:has-text('OK')",
        ]

        for selector in modal_close_selectors:
            try:
                close_button = await page.query_selector(selector)
                if close_button and await close_button.is_visible():
                    await close_button.click()
                    await asyncio.sleep(0.5)
                    logger.info(f"Dismissed modal using selector: {selector}")
                    break
            except Exception:
                continue

        # Also try pressing Escape key to close any modal
        try:
            await page.keyboard.press("Escape")
            await asyncio.sleep(0.3)
        except Exception:
            pass

    @staticmethod
    async def _scrape_theater_async(url: str) -> list[CinemarkMovieWithShowtimes]:
        """Async implementation of theater scraping with day clicking."""
        logger.info(f"Scraping Cinemark theater page: {url}")

        all_movies: list[CinemarkMovieWithShowtimes] = []

        async with AsyncCamoufox(headless=True) as browser:
            context = await browser.new_context()  # pyright: ignore[reportAttributeAccessIssue]
            page = await context.new_page()

            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )

                # Wait for the movie list to load
                await page.wait_for_selector(
                    ".list-movies .section-detail",
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )
                await asyncio.sleep(2)

                # Dismiss any modal dialogs that might be blocking interactions
                await CinemarkScraperAndHTMLParser._dismiss_modals(page)

                # Get all day buttons in the week selector
                day_buttons = await page.query_selector_all(".list-movies > .week .week__day")
                num_days = len(day_buttons)
                logger.info(f"Found {num_days} days in week selector")

                for day_index in range(num_days):
                    # Re-query day buttons after each click (DOM may have changed)
                    day_buttons = await page.query_selector_all(".list-movies > .week .week__day")
                    if day_index >= len(day_buttons):
                        break

                    day_button = day_buttons[day_index]

                    # Get the date from this day button
                    date_element = await day_button.query_selector(".week__date--small-font")
                    if not date_element:
                        logger.warning(f"No date element found for day {day_index}")
                        continue

                    date_text = await date_element.text_content()
                    if not date_text:
                        continue

                    selected_date = CinemarkScraperAndHTMLParser._parse_date_string(date_text)
                    if not selected_date:
                        logger.warning(f"Could not parse date: {date_text}")
                        continue

                    logger.info(f"Processing day {day_index + 1}/{num_days}: {selected_date}")

                    # Click on the day button
                    await day_button.click()
                    await asyncio.sleep(1.5)

                    # Get current page HTML and extract movies
                    html_content = await page.content()
                    movies_for_day = CinemarkScraperAndHTMLParser._parse_movies_from_cartelera_html(
                        html_content, selected_date
                    )

                    logger.info(f"Found {len(movies_for_day)} movies for {selected_date}")
                    all_movies.extend(movies_for_day)

            finally:
                await context.close()

        logger.info(f"Total movies collected across all days: {len(all_movies)}")
        return all_movies

    @staticmethod
    def _parse_date_string(date_text: str) -> datetime.date | None:
        """Parse date string like '27 ene. 2026' or '27 ene 2026'."""
        date_text = date_text.replace(".", " ").strip()

        match = re.match(r"(\d{1,2})\s+(\w{3})\s+(\d{4})", date_text)
        if not match:
            return None

        day = int(match.group(1))
        month_abbr = match.group(2).lower()
        year = int(match.group(3))

        month = SPANISH_MONTHS.get(month_abbr)
        if not month:
            return None

        try:
            return datetime.date(year, month, day)
        except ValueError:
            return None

    @staticmethod
    def _parse_movies_from_cartelera_html(
        html_content: str,
        selected_date: datetime.date,
    ) -> list[CinemarkMovieWithShowtimes]:
        """Extract movies and their showtimes from cartelera HTML."""
        soup = BeautifulSoup(html_content, "lxml")
        movies: list[CinemarkMovieWithShowtimes] = []

        # Find the .d-block container within .list-movies
        list_movies = soup.find(class_="list-movies")
        if not list_movies:
            logger.warning("Could not find .list-movies container")
            return movies

        d_block = list_movies.find(class_="d-block")  # pyright: ignore[reportAttributeAccessIssue]
        if not d_block:
            logger.warning("Could not find .d-block container")
            return movies

        # Find all section-detail divs (each represents a movie)
        section_details = d_block.find_all(class_="section-detail", recursive=False)  # pyright: ignore[reportAttributeAccessIssue]
        logger.debug(f"Found {len(section_details)} section-detail elements")

        for section in section_details:
            movie = CinemarkScraperAndHTMLParser._parse_movie_section(section, selected_date)
            if movie:
                movies.append(movie)

        return movies

    @staticmethod
    def _parse_movie_section(section: Tag, selected_date: datetime.date) -> CinemarkMovieWithShowtimes | None:
        """Parse a single movie section to extract title, URL, and showtimes."""
        # Get movie title from .section-detail__title (h2)
        title_elem = section.find(class_="section-detail__title")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)
        if not title or title.lower() in ("cargando", "horarios disponibles"):
            return None

        # Get movie URL from <a> with href containing /cartelera/
        links = section.find_all("a", href=True)
        link = None
        for a in links:
            href = str(a.get("href", ""))
            if "/cartelera/" in href:
                link = a
                break
        if not link:
            return None

        url = str(link.get("href", ""))
        if url.startswith("/"):
            url = "https://www.cinemark.com.co" + url

        # Parse showtimes from this section
        showtime_blocks = CinemarkScraperAndHTMLParser._parse_showtime_blocks(section)

        if not showtime_blocks:
            return None

        return CinemarkMovieWithShowtimes(
            title=title,
            url=url,
            date=selected_date,
            showtime_blocks=showtime_blocks,
        )

    @staticmethod
    def _parse_showtime_blocks(section: Tag) -> list[CinemarkShowtimeBlock]:
        """Parse showtime blocks from a movie section."""
        blocks: list[CinemarkShowtimeBlock] = []

        # Find all showtime containers (theater-detail__container--principal)
        containers = section.find_all(class_="theater-detail__container--principal")

        for container in containers:
            block = CinemarkScraperAndHTMLParser._parse_single_showtime_block(container)
            if block and block.times:
                blocks.append(block)

        return blocks

    @staticmethod
    def _parse_single_showtime_block(container: Tag) -> CinemarkShowtimeBlock | None:
        """Parse a single showtime block containing format, translation, seat type, and times."""
        header = container.find(class_="theaters-detail__header")
        if not header:
            return None

        # Extract format and translation type from formats__item spans
        format_items = header.find_all(class_="formats__item")
        format_str = "2D"
        translation_type = "Doblada"

        for i, item in enumerate(format_items):
            text = item.get_text(strip=True).lower()
            if i == 0:
                format_str = text.upper()
            elif i == 1:
                translation_type = text.capitalize()

        # Extract seat type (after "Sillas:" text)
        seat_type = "General"
        full_text = header.get_text()
        if "Sillas:" in full_text:
            # Look for text after "Sillas:" - typically "general" or "premier"
            spans = header.find_all("span")
            found_sillas = False
            for span in spans:
                text = span.get_text(strip=True).lower()
                if "sillas" in text:
                    found_sillas = True
                elif found_sillas and text and text not in ("", "2d", "3d", "doblada", "subtitulada", "subtitulado", "doblado"):
                    seat_type = text.capitalize()
                    break

        # Extract times from sessions__button--runtime
        times: list[datetime.time] = []
        time_buttons = container.find_all(class_="sessions__button--runtime")
        for btn in time_buttons:
            time_text = btn.get_text(strip=True)
            parsed_time = parse_time_string(time_text)
            if parsed_time:
                times.append(parsed_time)

        if not times:
            return None

        return CinemarkShowtimeBlock(
            format=format_str,
            translation_type=translation_type,
            seat_type=seat_type,
            times=times,
        )

    @staticmethod
    def generate_movie_source_url(movie_url: str) -> str:
        """Generate canonical movie URL for MovieSourceUrl storage.

        Converts cartelera URLs like https://www.cinemark.com.co/cartelera/medellin/movie-slug
        to canonical format: https://www.cinemark.com.co/movie-slug
        """
        slug = CinemarkScraperAndHTMLParser.extract_slug_from_url(movie_url)
        if slug:
            return f"https://www.cinemark.com.co/{slug}"
        return movie_url

    @staticmethod
    def extract_slug_from_url(url: str) -> str:
        """Extract movie slug from URL like https://www.cinemark.com.co/cartelera/medellin/movie-slug."""
        match = re.search(r"/cartelera/[^/]+/([^/?#]+)", url)
        if match:
            return match.group(1)
        # Fallback: try to get last path segment
        match = re.search(r"/([^/?#]+)$", url)
        if match:
            return match.group(1)
        return ""


class CinemarkShowtimeSaver(MovieAndShowtimeSaverTemplate):
    """Cinemark scraper that extends the template pattern."""

    def __init__(
        self,
        scraper: CinemarkScraperAndHTMLParser,
        tmdb_service: TMDBService,
        storage_service: SupabaseStorageService | None,
    ):
        super().__init__(
            tmdb_service=tmdb_service,
            storage_service=storage_service,
            source_name=SOURCE_NAME,
            scraper_type="cinemark",
            scraper_type_enum=MovieSourceUrl.ScraperType.CINEMARK,
            task_name=TASK_NAME,
        )
        self.scraper = scraper
        # Cache scraped data: url -> list of (date, showtime_blocks)
        self._movie_showtimes_cache: dict[str, list[tuple[datetime.date, list[CinemarkShowtimeBlock]]]] = {}

    def _find_movies(self, theater: Theater) -> list[MovieInfo]:
        """
        Scrape cartelera page and return list of movies with showtimes.

        This scrapes the entire theater page once, collecting movies for all days.
        The showtimes are cached for use in _process_showtimes_for_theater.
        """
        # Clear cache for this theater (cache is per-theater, not shared)
        self._movie_showtimes_cache.clear()

        cartelera_url = theater.download_source_url
        if not cartelera_url:
            logger.error(f"No download_source_url for theater {theater.name}")
            OperationalIssue.objects.create(
                name="Cinemark Missing Source URL",
                task=TASK_NAME,
                error_message=f"Theater {theater.name} has no download_source_url",
                context={"theater_slug": theater.slug},
                severity=OperationalIssue.Severity.ERROR,
            )
            return []

        try:
            movies_with_showtimes = self.scraper.scrape_theater_movies_and_showtimes(cartelera_url)
        except Exception as e:
            logger.error(f"Failed to scrape cartelera for {theater.name}: {e}")
            OperationalIssue.objects.create(
                name="Cinemark Scrape Failed",
                task=TASK_NAME,
                error_message=str(e),
                traceback=traceback.format_exc(),
                context={"cartelera_url": cartelera_url},
                severity=OperationalIssue.Severity.ERROR,
            )
            return []

        if not movies_with_showtimes:
            logger.warning(f"No movies found in cartelera for {theater.name}")
            OperationalIssue.objects.create(
                name="Cinemark No Movies Found",
                task=TASK_NAME,
                error_message=f"No movies found in cartelera for {theater.name}",
                context={"cartelera_url": cartelera_url},
                severity=OperationalIssue.Severity.WARNING,
            )
            return []

        # Build unique movie list and cache showtimes by URL
        seen_urls: set[str] = set()
        movies: list[MovieInfo] = []

        for movie_data in movies_with_showtimes:
            source_url = self.scraper.generate_movie_source_url(movie_data.url)

            # Cache showtimes for this movie
            if source_url not in self._movie_showtimes_cache:
                self._movie_showtimes_cache[source_url] = []
            self._movie_showtimes_cache[source_url].append(
                (movie_data.date, movie_data.showtime_blocks)
            )

            # Add to unique movie list
            if source_url not in seen_urls:
                seen_urls.add(source_url)
                movies.append(MovieInfo(name=movie_data.title, source_url=source_url))

        logger.info(f"Found {len(movies)} unique movies for {theater.name}")
        logger.info(f"Total movie/day combinations: {len(movies_with_showtimes)}\n\n")
        return movies

    def _get_movie_metadata(self, movie_info: MovieInfo) -> MovieMetadata | None:
        """
        Return None - we don't need to visit individual movie pages for metadata.

        TMDB service will be used to get movie metadata via the base class.
        """
        return None

    def _process_showtimes_for_theater(
        self,
        theater: Theater,
        movies_for_theater: list[MovieInfo],
        movies_cache: dict[str, Movie | None],
    ) -> int:
        """Use cached showtime data to create showtimes for each movie."""
        logger.info(f"Processing showtimes for Cinemark theater: {theater.name}")

        all_showtimes: list[ShowtimeData] = []

        for movie_info in movies_for_theater:
            movie = movies_cache.get(movie_info.source_url)
            if not movie:
                logger.debug(f"Skipping showtimes for unfindable movie: {movie_info.name}")
                continue

            cached_data = self._movie_showtimes_cache.get(movie_info.source_url, [])
            if not cached_data:
                logger.warning(f"No cached showtime data for {movie_info.name}")
                continue

            for date, showtime_blocks in cached_data:
                for block in showtime_blocks:
                    translation_type = normalize_translation_type(
                        block.translation_type,
                        task=TASK_NAME,
                        context={"theater": theater.name, "movie": movie.title_es},
                    )

                    for time in block.times:
                        all_showtimes.append(ShowtimeData(
                            movie=movie,
                            date=date,
                            time=time,
                            format=block.format,
                            translation_type=translation_type,
                            screen=block.seat_type,
                            source_url=movie_info.source_url,
                        ))

        logger.info(f"Collected {len(all_showtimes)} showtimes for {theater.name}")
        return self._save_showtimes_for_theater(theater, all_showtimes)


@app.task
def cinemark_download_task():
    """Celery task to download Cinemark showtimes."""
    logger.info("Starting cinemark_download_task\n")

    try:
        scraper = CinemarkScraperAndHTMLParser()
        tmdb_service = TMDBService()
        storage_service = SupabaseStorageService.create_from_settings()
        if not storage_service:
            raise RuntimeError("Failed to create storage service")

        saver = CinemarkShowtimeSaver(scraper, tmdb_service, storage_service)
        report = saver.execute()
        report.print_report()
        return report

    except Exception as e:
        logger.error(f"Failed Cinemark download task: {e}")
        OperationalIssue.objects.create(
            name="Cinemark Download Task Failed",
            task=TASK_NAME,
            error_message=str(e),
            traceback=traceback.format_exc(),
            context={},
            severity=OperationalIssue.Severity.ERROR,
        )
        raise
