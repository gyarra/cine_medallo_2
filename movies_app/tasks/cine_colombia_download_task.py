"""
Cine Colombia Scraper Task

Celery task for scraping movie showtime data from Cine Colombia theaters.

Theater pages are at: https://www.cinecolombia.com/cinemas/{theater_slug}/
Movie detail pages are at: https://www.cinecolombia.com/films/{movie_slug}/{movie_id}/

The theater page displays:
- A date picker (.v-date-picker) with clickable date buttons
- Movies list (.v-showtime-picker-film-list) with showtimes for the selected date
- Each movie has its own showtime list with format/language attributes

This scraper:
1. Loads the theater page
2. Clicks through each date in the date picker (active dates only)
3. Extracts movies and their showtimes for each date
4. Collects all unique movies across all dates
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
    fetch_page_html,
    normalize_translation_type,
    parse_time_string,
)
from movies_app.tasks.movie_and_showtime_saver_template import (
    MovieAndShowtimeSaverTemplate,
    MovieInfo,
    ShowtimeData,
)

if TYPE_CHECKING:
    from playwright.async_api import ElementHandle, Page

logger = logging.getLogger(__name__)

SOURCE_NAME = "cine_colombia"
TASK_NAME = "cine_colombia_download_task"

SPANISH_MONTHS = {
    "ene": 1, "feb": 2, "mar": 3, "abr": 4,
    "may": 5, "jun": 6, "jul": 7, "ago": 8,
    "sep": 9, "oct": 10, "nov": 11, "dic": 12,
}


@dataclass
class CineColombiaMovie:
    """Movie info extracted from showtime picker."""
    film_id: str
    title: str
    url: str


@dataclass
class CineColombiaShowtime:
    """Showtime data extracted from the page."""
    time: datetime.time
    screen: str
    format: str
    translation_type: str


@dataclass
class CineColombiaMovieWithShowtimes:
    """Movie data with showtimes for a specific date."""
    film_id: str
    title: str
    url: str
    date: datetime.date
    showtimes: list[CineColombiaShowtime] = field(default_factory=list)


class CineColombiaScraperAndHTMLParser:
    """
    Scraper that uses Playwright to interact with Cine Colombia pages.

    The Cine Colombia page is a SPA that requires JavaScript interaction:
    - Movies are displayed in .v-showtime-picker-film-list items
    - A date picker (.v-date-picker) allows clicking different dates
    - Showtimes include attributes for format (2D/3D) and language (Doblada/Subtitulada)
    """

    @staticmethod
    def scrape_theater_movies_and_showtimes(url: str) -> list[CineColombiaMovieWithShowtimes]:
        """
        Scrape all movies and showtimes from theater page.

        Clicks through each active date in the date picker to collect all movies and showtimes.
        """
        return asyncio.run(CineColombiaScraperAndHTMLParser._scrape_theater_async(url))

    @staticmethod
    async def _dismiss_modals(page: Page) -> None:
        """
        Dismiss modal dialogs that block interactions.

        There are two modals to handle:
        1. Cookie consent notification - has "Aceptar" button in .v-notification
        2. City selection modal - requires selecting city from dropdown then clicking "Confirmar"
        """

        # 2. Handle city selection modal
        for attempt in range(3):
            try:
                modal = await page.query_selector(".required-cinema-group-prompt")
                if not modal or not await modal.is_visible():
                    return

                logger.info(f"City selection modal detected (attempt {attempt + 1})")

                # The modal has a dropdown button that needs to be clicked first
                dropdown_button = await modal.query_selector(".v-dropdown-button")
                if dropdown_button:
                    await dropdown_button.click()
                    await asyncio.sleep(0.2)

                    # Wait for dropdown list to appear and select Medellín
                    medellin_option = await page.query_selector(
                        ".v-dropdown-list-item:has-text('Medellín')"
                    )
                    if medellin_option:
                        await medellin_option.click()
                        await asyncio.sleep(0.2)

                        # Now the Confirmar button should be enabled
                        confirm_button = await modal.query_selector(
                            ".required-cinema-group-prompt__submit-button"
                        )
                        if confirm_button:
                            await confirm_button.click()
                            # Wait for modal to disappear
                            try:
                                await page.wait_for_selector(
                                    ".required-cinema-group-prompt",
                                    state="hidden",
                                    timeout=3000,
                                )
                                logger.info("City selection modal dismissed")
                                return
                            except Exception:
                                await asyncio.sleep(0.3)
                                continue
            except Exception as e:
                logger.debug(f"Error dismissing city modal (attempt {attempt + 1}): {e}")
                await asyncio.sleep(0.3)

    @staticmethod
    async def _scrape_theater_async(url: str) -> list[CineColombiaMovieWithShowtimes]:
        """Async implementation of theater scraping with date clicking."""
        logger.info(f"Scraping Cine Colombia theater page: {url}")

        all_movies: list[CineColombiaMovieWithShowtimes] = []

        async with AsyncCamoufox(headless=True) as browser:
            # Deny geolocation permission to avoid browser prompt
            context = await browser.new_context(  # pyright: ignore[reportAttributeAccessIssue]
                permissions=[],
                geolocation=None,
            )
            page = await context.new_page()

            try:
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )

                # Wait briefly for page to stabilize, then dismiss modals immediately
                await asyncio.sleep(1)
                await CineColombiaScraperAndHTMLParser._dismiss_modals(page)

                # Now wait for the film list to load (should be fast after modal dismissed)
                await page.wait_for_selector(
                    ".v-showtime-picker-film-list",
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )

                date_buttons = await page.query_selector_all(".v-date-picker-date")
                num_dates = len(date_buttons)
                logger.info(f"Found {num_dates} dates in date picker")

                for date_index in range(num_dates):
                    date_buttons = await page.query_selector_all(".v-date-picker-date")
                    if date_index >= len(date_buttons):
                        break

                    date_button = date_buttons[date_index]

                    button_element = await date_button.query_selector("button")
                    if not button_element:
                        continue

                    button_class = await button_element.get_attribute("class") or ""
                    if "v-date-picker-date__button--inactive" in button_class:
                        logger.debug(f"Skipping inactive date at index {date_index}")
                        continue

                    selected_date = await CineColombiaScraperAndHTMLParser._extract_date_from_button(
                        date_button
                    )
                    if not selected_date:
                        logger.warning(f"Could not extract date at index {date_index}")
                        continue

                    logger.info(f"Processing date {date_index + 1}/{num_dates}: {selected_date}")

                    # Try to click the date button, scrolling into view if needed
                    try:
                        await button_element.scroll_into_view_if_needed()
                        await button_element.click(timeout=5000)
                    except Exception:
                        # If button is outside viewport, try clicking the "next" arrow
                        next_arrow = await page.query_selector(".v-date-picker__arrow--next")
                        if next_arrow:
                            await next_arrow.click()
                            await asyncio.sleep(0.3)
                            # Re-fetch buttons and try again
                            date_buttons = await page.query_selector_all(".v-date-picker-date")
                            if date_index < len(date_buttons):
                                date_button = date_buttons[date_index]
                                button_element = await date_button.query_selector("button")
                                if button_element:
                                    await button_element.click(timeout=5000)

                    # Wait for content to update after clicking date
                    await asyncio.sleep(0.8)

                    html_content = await page.content()
                    movies_for_date = CineColombiaScraperAndHTMLParser._parse_movies_from_html(
                        html_content, selected_date
                    )

                    logger.info(f"Found {len(movies_for_date)} movies for {selected_date}")
                    all_movies.extend(movies_for_date)

            finally:
                await context.close()

        logger.info(f"Total movies collected across all dates: {len(all_movies)}")
        return all_movies

    @staticmethod
    async def _extract_date_from_button(date_button: ElementHandle) -> datetime.date | None:
        """Extract date from a date picker button element."""
        today_label = await date_button.query_selector(".v-date-picker-date__label--today")
        if today_label:
            return datetime.date.today()

        day_elem = await date_button.query_selector(".v-date-picker-date__day-of-month")
        month_elem = await date_button.query_selector(".v-date-picker-date__month")

        if not day_elem or not month_elem:
            return None

        day_text = await day_elem.text_content()
        month_text = await month_elem.text_content()

        if not day_text or not month_text:
            return None

        day = int(day_text.strip())
        month_abbr = month_text.strip().lower()
        month = SPANISH_MONTHS.get(month_abbr)

        if not month:
            return None

        year = datetime.date.today().year
        try:
            parsed_date = datetime.date(year, month, day)
            if parsed_date < datetime.date.today() - datetime.timedelta(days=30):
                parsed_date = datetime.date(year + 1, month, day)
            return parsed_date
        except ValueError:
            return None

    @staticmethod
    def _parse_movies_from_html(
        html_content: str,
        selected_date: datetime.date,
    ) -> list[CineColombiaMovieWithShowtimes]:
        """Extract movies and their showtimes from the theater page HTML."""
        soup = BeautifulSoup(html_content, "lxml")
        movies: list[CineColombiaMovieWithShowtimes] = []

        film_items = soup.find_all("li", class_="v-showtime-picker-film-list__item")

        for film_item in film_items:
            movie = CineColombiaScraperAndHTMLParser._parse_film_item(film_item, selected_date)
            if movie and movie.showtimes:
                movies.append(movie)

        return movies

    @staticmethod
    def _parse_film_item(
        film_item: Tag,
        selected_date: datetime.date,
    ) -> CineColombiaMovieWithShowtimes | None:
        """Parse a single film item from the showtime picker."""
        item_id = film_item.get("id", "")
        if not isinstance(item_id, str):
            return None

        match = re.search(r"film-id-(\w+)", item_id)
        if not match:
            return None
        film_id = match.group(1)

        title_elem = film_item.find("h3", class_="v-film-title__text")
        if not title_elem:
            return None
        title_parts = [
            child for child in title_elem.children
            if isinstance(child, str) and child.strip()
        ]
        title = title_parts[0].strip() if title_parts else title_elem.get_text(strip=True)

        link_elem = film_item.find("a", class_="v-showtime-picker-film-thumbnail__link")
        url = ""
        if link_elem:
            href = link_elem.get("href")
            if isinstance(href, str):
                url = f"https://www.cinecolombia.com{href}" if href.startswith("/") else href

        showtimes = CineColombiaScraperAndHTMLParser._parse_showtimes(film_item)

        return CineColombiaMovieWithShowtimes(
            film_id=film_id,
            title=title,
            url=url,
            date=selected_date,
            showtimes=showtimes,
        )

    @staticmethod
    def _extract_attributes_from_icons(icons: list[Tag]) -> tuple[str, str]:
        """Extract format and translation type from attribute icon images."""
        format_type = "2D"
        translation_type = ""

        for icon in icons:
            alt = icon.get("alt", "")
            title_attr = icon.get("title", "")
            alt_str = alt if isinstance(alt, str) else ""
            title_str = title_attr if isinstance(title_attr, str) else ""
            attr_text = (alt_str or title_str).lower()

            if "3d" in attr_text:
                format_type = "3D"
            elif "2d" in attr_text:
                format_type = "2D"
            elif "doblada" in attr_text or "doblado" in attr_text:
                translation_type = "DOB"
            elif "subtitulada" in attr_text or "subtitulado" in attr_text:
                translation_type = "SUB"

        return format_type, translation_type

    @staticmethod
    def _parse_showtimes(film_item: Tag) -> list[CineColombiaShowtime]:
        """Extract showtimes from a film item."""
        showtimes: list[CineColombiaShowtime] = []

        common_attrs = film_item.find("div", class_="v-showtime-picker-site__common-attributes")
        common_format = "2D"
        common_translation = ""
        if common_attrs:
            common_icons = common_attrs.find_all("img", class_="v-image__img")
            common_format, common_translation = (
                CineColombiaScraperAndHTMLParser._extract_attributes_from_icons(common_icons)
            )

        showtime_buttons = film_item.find_all("a", class_="v-showtime-button")

        for button in showtime_buttons:
            time_elem = button.find("time", class_="v-showtime-button__detail-start-time")
            if not time_elem:
                continue

            time_text = time_elem.get_text(strip=True)
            ampm_elem = button.find("span", class_="v-showtime-button__detail-start-time-ampm")
            ampm = ampm_elem.get_text(strip=True) if ampm_elem else ""

            full_time_str = f"{time_text} {ampm}".strip()
            parsed_time = parse_time_string(full_time_str)
            if not parsed_time:
                continue

            screen_elem = button.find("div", class_="v-showtime-button__screen-name")
            screen = screen_elem.get_text(strip=True) if screen_elem else ""

            attr_list = button.find("ul", class_="v-showtime-button__attribute-list")
            button_icons: list[Tag] = []
            if attr_list:
                button_icons = attr_list.find_all("img", class_="v-image__img")

            if button_icons:
                format_type, translation_type = (
                    CineColombiaScraperAndHTMLParser._extract_attributes_from_icons(button_icons)
                )
            else:
                format_type = common_format
                translation_type = common_translation

            showtimes.append(CineColombiaShowtime(
                time=parsed_time,
                screen=screen,
                format=format_type,
                translation_type=translation_type,
            ))

        return showtimes

    @staticmethod
    def download_movie_detail_html(url: str) -> str:
        """Download movie detail page HTML."""
        return fetch_page_html(url, wait_selector=".v-film-details", sleep_seconds_after_wait=1)

    @staticmethod
    def parse_movie_metadata(html_content: str) -> MovieMetadata | None:
        """Extract movie metadata from detail page HTML."""
        soup = BeautifulSoup(html_content, "lxml")

        film_details = soup.find(class_="v-film-details")
        if not film_details:
            return None

        original_title: str | None = None
        director: str = ""
        actors: list[str] = []
        duration_minutes: int | None = None
        genre: str = ""
        classification: str = ""
        release_date: datetime.date | None = None
        release_year: int | None = None

        title_elem = soup.find("h1", class_="v-film-title__text")
        if title_elem:
            title_text = title_elem.get_text(strip=True)
            match = re.search(r"\(([^)]+)\)$", title_text)
            if match:
                original_title = match.group(1)

        info_items = soup.find_all(class_="v-film-info-item")
        for item in info_items:
            label_elem = item.find(class_="v-film-info-item__label")
            value_elem = item.find(class_="v-film-info-item__value")
            if not label_elem or not value_elem:
                continue

            label = label_elem.get_text(strip=True).lower()
            value = value_elem.get_text(strip=True)

            if "director" in label:
                director = value
            elif "reparto" in label or "cast" in label or "actores" in label:
                actors = [a.strip() for a in value.split(",") if a.strip()]
            elif "duración" in label or "duration" in label:
                duration_match = re.search(r"(\d+)", value)
                if duration_match:
                    duration_minutes = int(duration_match.group(1))
            elif "género" in label or "genre" in label:
                genre = value
            elif "clasificación" in label or "rating" in label:
                classification = value
            elif "estreno" in label or "release" in label:
                year_match = re.search(r"(\d{4})", value)
                if year_match:
                    release_year = int(year_match.group(1))

        return MovieMetadata(
            genre=genre,
            duration_minutes=duration_minutes,
            classification=classification,
            director=director,
            actors=actors,
            original_title=original_title,
            release_date=release_date,
            release_year=release_year,
            trailer_url=None,
        )

    @staticmethod
    def generate_movie_source_url(film_id: str) -> str:
        """Generate canonical source URL for a movie."""
        return f"https://www.cinecolombia.com/films/{film_id}"


class CineColombiaShowtimeSaver(MovieAndShowtimeSaverTemplate):
    """Cine Colombia scraper that extends the template pattern."""

    def __init__(
        self,
        scraper: CineColombiaScraperAndHTMLParser,
        tmdb_service: TMDBService,
        storage_service: SupabaseStorageService | None,
    ):
        super().__init__(
            tmdb_service=tmdb_service,
            storage_service=storage_service,
            source_name=SOURCE_NAME,
            scraper_type="cine_colombia",
            scraper_type_enum=MovieSourceUrl.ScraperType.CINE_COLOMBIA,
            task_name=TASK_NAME,
        )
        self.scraper = scraper
        self._movie_showtimes_cache: dict[str, list[CineColombiaMovieWithShowtimes]] = {}

    def _find_movies(self, theater: Theater) -> list[MovieInfo]:
        """Download theater page and return list of movies."""
        self._movie_showtimes_cache.clear()

        url = theater.download_source_url
        all_movies = self.scraper.scrape_theater_movies_and_showtimes(url)

        movies_by_id: dict[str, CineColombiaMovie] = {}
        for movie_data in all_movies:
            if movie_data.film_id not in movies_by_id:
                movies_by_id[movie_data.film_id] = CineColombiaMovie(
                    film_id=movie_data.film_id,
                    title=movie_data.title,
                    url=movie_data.url,
                )

            if movie_data.film_id not in self._movie_showtimes_cache:
                self._movie_showtimes_cache[movie_data.film_id] = []
            self._movie_showtimes_cache[movie_data.film_id].append(movie_data)

        logger.info(
            f"Found {len(all_movies)} movie-date combinations, "
            f"{len(movies_by_id)} unique movies\n\n"
        )

        movie_infos: list[MovieInfo] = []
        for movie in movies_by_id.values():
            source_url = self.scraper.generate_movie_source_url(movie.film_id)
            movie_infos.append(MovieInfo(
                name=movie.title,
                source_url=source_url,
            ))

        return movie_infos

    def _get_movie_metadata(self, movie_info: MovieInfo) -> MovieMetadata | None:
        """Fetch metadata from movie detail page."""
        film_id = movie_info.source_url.split("/")[-1]

        for movie_data_list in self._movie_showtimes_cache.values():
            for movie_data in movie_data_list:
                if movie_data.film_id == film_id and movie_data.url:
                    try:
                        html_content = self.scraper.download_movie_detail_html(movie_data.url)
                        return self.scraper.parse_movie_metadata(html_content)
                    except Exception as e:
                        logger.warning(f"Failed to fetch metadata for {movie_info.name}: {e}")
                        return None

        return None

    def _process_showtimes_for_theater(
        self,
        theater: Theater,
        movies_for_theater: list[MovieInfo],
        movies_cache: dict[str, Movie | None],
    ) -> int:
        """Build showtimes from cached data and save to database."""
        logger.info(f"Processing Cine Colombia theater: {theater.name}\n\n")

        showtimes: list[ShowtimeData] = []

        for movie_info in movies_for_theater:
            movie = movies_cache.get(movie_info.source_url)
            if not movie:
                continue

            film_id = movie_info.source_url.split("/")[-1]
            movie_data_list = self._movie_showtimes_cache.get(film_id, [])

            for movie_data in movie_data_list:
                for st in movie_data.showtimes:
                    translation_type = normalize_translation_type(
                        st.translation_type,
                        task=TASK_NAME,
                        context={"theater": theater.name, "movie": movie.title_es},
                    )
                    showtimes.append(ShowtimeData(
                        movie=movie,
                        date=movie_data.date,
                        time=st.time,
                        format=st.format,
                        translation_type=translation_type,
                        screen=st.screen,
                        source_url=theater.download_source_url or "",
                    ))

        return self._save_showtimes_for_theater(theater, showtimes)


@app.task
def cine_colombia_download_task():
    logger.info("Starting cine_colombia_download_task\n")

    try:
        scraper = CineColombiaScraperAndHTMLParser()
        tmdb_service = TMDBService()
        storage_service = SupabaseStorageService.create_from_settings()
        if not storage_service:
            raise RuntimeError("Failed to create storage service")

        saver = CineColombiaShowtimeSaver(scraper, tmdb_service, storage_service)
        report = saver.execute()
        report.print_report()
        return report

    except Exception as e:
        logger.error(f"Failed Cine Colombia download task: {e}")
        OperationalIssue.objects.create(
            name="Cine Colombia Download Task Failed",
            task=TASK_NAME,
            error_message=str(e),
            traceback=traceback.format_exc(),
            context={},
            severity=OperationalIssue.Severity.ERROR,
        )
        raise
