"""
Royal Films Scraper Task

Celery task for scraping movie showtime data from Royal Films theaters.

The cartelera (theater page) is at: https://cinemasroyalfilms.com/cartelera/{city}/{theater_slug}
Individual movie pages are at: https://cinemasroyalfilms.com/pelicula/{movie_id}/{movie_slug}

Movies are listed on the theater page. Showtimes for each movie are on the individual
movie page, organized by theater and date in an accordion UI.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from camoufox.async_api import AsyncCamoufox
from django.conf import settings
from django.db import transaction

from config.celery_app import app
from movies_app.models import Movie, MovieSourceUrl, OperationalIssue, Showtime, Theater
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.download_utilities import (
    BOGOTA_TZ,
    BROWSER_TIMEOUT_SECONDS,
    SPANISH_MONTHS_ABBREVIATIONS,
    MovieMetadata,
    normalize_translation_type,
    parse_time_string,
)
from movies_app.tasks.movie_and_showtime_saver_template import (
    MovieAndShowtimeSaverTemplate,
    MovieInfo,
    ShowtimeData,
    TaskReport,
)

logger = logging.getLogger(__name__)

SOURCE_NAME = "royal"
TASK_NAME = "royal_download_task"
ROYAL_BASE_URL = "https://cinemasroyalfilms.com"
ROYAL_CONTEXT_FILE = Path(settings.BASE_DIR) / ".royal_browser_context.json"


@dataclass
class RoyalMovieCard:
    movie_id: str
    title: str
    slug: str
    url: str
    poster_url: str


@dataclass
class RoyalShowtime:
    date: datetime.date
    time: datetime.time
    format: str
    translation_type: str


class RoyalScraperAndHTMLParser:
    """Stateless class for fetching and parsing Royal Films web pages."""

    _context_initialized: bool = False

    @staticmethod
    def _load_storage_state() -> dict[str, Any] | None:
        """Load saved browser storage state (cookies, localStorage) if it exists."""
        if ROYAL_CONTEXT_FILE.exists():
            try:
                with open(ROYAL_CONTEXT_FILE, "r") as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError) as e:
                logger.warning(f"Failed to load browser context: {e}")
        return None

    @staticmethod
    def _save_storage_state(storage_state: Any) -> None:
        """Save browser storage state for future use."""
        try:
            with open(ROYAL_CONTEXT_FILE, "w") as f:
                json.dump(storage_state, f)
            logger.info("Saved Royal Films browser context for future use")
        except OSError as e:
            logger.warning(f"Failed to save browser context: {e}")

    @staticmethod
    async def _dismiss_city_modal_if_present(page: object) -> bool:
        """
        Check if the city selection modal is visible and dismiss it if possible.

        Returns True if modal was dismissed, False if no modal was present.
        """
        try:
            # Check if the city selection modal is visible
            modal = await page.query_selector(".modal-dialog")  # pyright: ignore[reportAttributeAccessIssue]
            if not modal:
                return False

            # Check if it's visible (not hidden)
            is_visible = await modal.is_visible()  # pyright: ignore[reportAttributeAccessIssue]
            if not is_visible:
                return False

            logger.info("City selection modal detected, selecting Medellín...")
            return True
        except Exception:
            return False

    @staticmethod
    async def _select_colombia_city_async(page: object) -> None:
        """
        Select Colombia as the country on the Royal Films city selection page.

        Royal Films requires selecting a country/city before showing movie content.
        This method handles the city selection dialog that appears on first visit.
        """
        await asyncio.sleep(2)

        # Check if city selection dialog is present
        try:
            dropdown = await page.query_selector(".nice-select")  # pyright: ignore[reportAttributeAccessIssue]
            if not dropdown:
                return

            # Click country dropdown
            await page.click(".nice-select", timeout=5000)  # pyright: ignore[reportAttributeAccessIssue]
            await asyncio.sleep(1)

            # Select Colombia (value="1")
            await page.click('li.option[value="1"]', timeout=5000)  # pyright: ignore[reportAttributeAccessIssue]
            await asyncio.sleep(2)

            # Check if city dropdown appeared (2nd dropdown)
            dropdowns = await page.query_selector_all(".nice-select")  # pyright: ignore[reportAttributeAccessIssue]
            if len(dropdowns) >= 2:
                await dropdowns[1].click()
                await asyncio.sleep(1)

                # Select Medellín
                await page.click('li.option:has-text("Medellín")', timeout=5000)  # pyright: ignore[reportAttributeAccessIssue]
                await asyncio.sleep(1)

            # Click the select location button
            await page.click(".btn-selection", timeout=5000)  # pyright: ignore[reportAttributeAccessIssue]
            await asyncio.sleep(3)
        except Exception:
            # City selection may not be needed if already selected (via cookies)
            pass

    @staticmethod
    async def _fetch_royal_page_async(
        url: str,
        wait_selector: str,
        optional_selector: bool = False,
    ) -> str:
        """
        Fetch a Royal Films page, handling city selection if needed.

        Royal Films is an Angular SPA that requires selecting a country/city
        before showing movie content. This method uses saved browser context
        to skip city selection when possible.

        Args:
            url: The URL to fetch
            wait_selector: CSS selector to wait for before returning HTML
            optional_selector: If True, don't fail if selector is not found
        """
        logger.info(f"Scraping Royal Films page: {url}")

        # Try to load existing storage state
        storage_state = RoyalScraperAndHTMLParser._load_storage_state()
        need_city_selection = storage_state is None

        async with AsyncCamoufox(headless=True) as browser:
            # Create context with saved state if available
            if storage_state:
                context = await browser.new_context(  # pyright: ignore[reportAttributeAccessIssue]
                    ignore_https_errors=True,
                    storage_state=storage_state,  # pyright: ignore[reportArgumentType]
                )
            else:
                context = await browser.new_context(ignore_https_errors=True)  # pyright: ignore[reportAttributeAccessIssue]

            page = await context.new_page()

            try:
                if need_city_selection:
                    # First, go to main page to handle city selection
                    await page.goto(
                        ROYAL_BASE_URL,
                        wait_until="domcontentloaded",
                        timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                    )

                    await RoyalScraperAndHTMLParser._select_colombia_city_async(page)

                    # Save storage state after city selection
                    saved_state = await context.storage_state()  # pyright: ignore[reportAttributeAccessIssue]
                    RoyalScraperAndHTMLParser._save_storage_state(saved_state)

                # Navigate to the target URL
                await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                )

                # Check if city modal appeared (can happen even with saved state)
                await asyncio.sleep(1)
                modal_present = await RoyalScraperAndHTMLParser._dismiss_city_modal_if_present(page)
                if modal_present:
                    await RoyalScraperAndHTMLParser._select_colombia_city_async(page)
                    # Update saved state since we had to re-select
                    saved_state = await context.storage_state()  # pyright: ignore[reportAttributeAccessIssue]
                    RoyalScraperAndHTMLParser._save_storage_state(saved_state)

                # Wait for selector (with optional fallback)
                try:
                    await page.wait_for_selector(
                        wait_selector,
                        timeout=BROWSER_TIMEOUT_SECONDS * 1000,
                    )
                except Exception:
                    if not optional_selector:
                        raise
                    # This typically means movie has no showtimes in Medellín
                    logger.debug(f"Selector '{wait_selector}' not found on {url} - likely no showtimes")

                await asyncio.sleep(2)

                html_content: str = await page.content()
            finally:
                await context.close()

        return html_content

    @staticmethod
    def download_theater_page_html(url: str) -> str:
        return asyncio.run(
            RoyalScraperAndHTMLParser._fetch_royal_page_async(
                url,
                wait_selector=".prs_upcom_movie_box_wrapper",
            )
        )

    @staticmethod
    def download_movie_page_html(url: str) -> str:
        """
        Download movie page HTML.

        Uses optional_selector=True because some movies may not have showtimes
        in Medellín and won't have the #accordionFunctions element.
        """
        return asyncio.run(
            RoyalScraperAndHTMLParser._fetch_royal_page_async(
                url,
                wait_selector="#accordionFunctions",
                optional_selector=True,
            )
        )

    @staticmethod
    def parse_movies_from_theater_html(html_content: str) -> list[RoyalMovieCard]:
        """Parse movies from the theater's cartelera page."""
        soup = BeautifulSoup(html_content, "lxml")
        movies: list[RoyalMovieCard] = []
        seen_urls: set[str] = set()

        billboard_tab = soup.find("div", id="billboard")
        if not billboard_tab:
            billboard_tab = soup

        movie_boxes = billboard_tab.find_all("div", class_="prs_upcom_movie_box_wrapper")

        for box in movie_boxes:
            img_box = box.find("div", class_="prs_upcom_movie_img_box")
            if not img_box:
                continue

            link = img_box.find("a", href=True)
            if not link:
                continue

            href = str(link.get("href", ""))
            if not href.startswith("/pelicula/"):
                continue

            if href in seen_urls:
                continue
            seen_urls.add(href)

            movie_id, slug = RoyalScraperAndHTMLParser._extract_movie_id_and_slug(href)
            if not movie_id:
                continue

            title_elem = box.find("h2")
            if title_elem:
                title_link = title_elem.find("a")
                if title_link:
                    title = title_link.get_text(strip=True)
                else:
                    title = title_elem.get_text(strip=True)
            else:
                title = slug.replace("-", " ").title()

            img_elem = img_box.find("img")
            poster_url = ""
            if img_elem:
                poster_url = str(img_elem.get("src", ""))

            full_url = f"{ROYAL_BASE_URL}{href}"

            movies.append(RoyalMovieCard(
                movie_id=movie_id,
                title=title,
                slug=slug,
                url=full_url,
                poster_url=poster_url,
            ))

        return movies

    @staticmethod
    def _extract_movie_id_and_slug(href: str) -> tuple[str, str]:
        """Extract movie ID and slug from href like /pelicula/3889/sin-piedad."""
        match = re.match(r"/pelicula/(\d+)/(.+)", href)
        if match:
            return match.group(1), match.group(2)
        return "", ""

    @staticmethod
    def has_no_showtimes_message(html_content: str) -> bool:
        """Check if the page shows 'No se encontró ninguna función' message."""
        return "No se encontró ninguna función" in html_content

    @staticmethod
    def parse_available_dates_from_movie_html(html_content: str) -> list[datetime.date]:
        """Parse available dates from the movie page calendar tabs."""
        soup = BeautifulSoup(html_content, "lxml")
        dates: list[datetime.date] = []
        today = datetime.datetime.now(BOGOTA_TZ).date()
        reference_year = today.year

        date_tabs = soup.find_all("li", class_="item-day")

        for tab in date_tabs:
            link = tab.find("a")
            if not link:
                continue

            date_text = link.get_text(strip=True)
            parsed_date = RoyalScraperAndHTMLParser._parse_date_tab_text(date_text, reference_year)
            if parsed_date:
                delta = (parsed_date - today).days
                if delta > 180:
                    parsed_date = parsed_date.replace(year=parsed_date.year - 1)
                elif delta < -180:
                    parsed_date = parsed_date.replace(year=parsed_date.year + 1)
                dates.append(parsed_date)

        return dates

    @staticmethod
    def _parse_date_tab_text(date_text: str, reference_year: int) -> datetime.date | None:
        """Parse date text like 'mar 27 ene' or 'mar27 ene' (no space after day name)."""
        date_text = date_text.lower().strip()
        date_text = re.sub(r"\s+", " ", date_text)

        # Match formats: "27 ene" or "mar27 ene" or "mar 27 ene"
        match = re.search(r"(\d{1,2})\s*(\w{3})", date_text)
        if not match:
            return None

        day = int(match.group(1))
        month_abbr = match.group(2)

        month = SPANISH_MONTHS_ABBREVIATIONS.get(month_abbr)
        if not month:
            return None

        try:
            return datetime.date(reference_year, month, day)
        except ValueError:
            return None

    @staticmethod
    def parse_showtimes_from_movie_html(
        html_content: str,
        theater_name: str,
        selected_date: datetime.date,
    ) -> list[RoyalShowtime]:
        """Parse showtimes for a specific theater and date from the movie page."""
        soup = BeautifulSoup(html_content, "lxml")
        showtimes: list[RoyalShowtime] = []

        accordion = soup.find("div", id="accordionFunctions")
        if not accordion:
            return []

        panels = accordion.find_all("div", class_="panel-default")

        for panel in panels:
            header = panel.find("h4", class_="panel-title")
            if not header:
                continue

            panel_theater_link = header.find("a")
            if not panel_theater_link:
                continue

            panel_theater_name = panel_theater_link.get_text(strip=True)
            if not RoyalScraperAndHTMLParser._theater_names_match(panel_theater_name, theater_name):
                continue

            panel_body = panel.find("div", class_="panel-body")
            if not panel_body:
                continue

            schedule_rows = panel_body.find_all("div", class_="st_calender_asc")

            for row in schedule_rows:
                format_header = row.find("h3")
                format_str = ""
                translation_type = ""

                if format_header:
                    format_text = format_header.get_text(strip=True)
                    format_str, translation_type = RoyalScraperAndHTMLParser._parse_format_and_translation(format_text)

                time_list = row.find("ul")
                if not time_list:
                    continue

                time_items = time_list.find_all("li")
                for time_item in time_items:
                    time_link = time_item.find("a")
                    if not time_link:
                        continue

                    time_text = time_link.get_text(strip=True)
                    parsed_time = RoyalScraperAndHTMLParser._parse_royal_time(time_text)
                    if not parsed_time:
                        logger.warning(f"Could not parse time: {time_text}")
                        continue

                    showtimes.append(RoyalShowtime(
                        date=selected_date,
                        time=parsed_time,
                        format=format_str,
                        translation_type=translation_type,
                    ))

        return showtimes

    @staticmethod
    def _theater_names_match(panel_name: str, theater_name: str) -> bool:
        """Check if panel theater name matches the target theater."""
        panel_normalized = panel_name.lower().strip()
        theater_normalized = theater_name.lower().strip()

        for prefix in ["multicine ", "royal films - multicine ", "royal films - "]:
            panel_normalized = panel_normalized.replace(prefix, "")
            theater_normalized = theater_normalized.replace(prefix, "")

        if panel_normalized == theater_normalized:
            return True

        # Check if one contains the other (for slight variations)
        if panel_normalized in theater_normalized or theater_normalized in panel_normalized:
            return True

        return False

    @staticmethod
    def _parse_format_and_translation(format_text: str) -> tuple[str, str]:
        """Parse format text like '2D - DOB' into format and translation type.

        Returns the raw translation type value - normalization happens in the saver.
        """
        format_text = format_text.strip()
        parts = [p.strip() for p in format_text.split("-") if p.strip()]

        format_str = ""
        translation_type = ""

        for part in parts:
            upper_part = part.upper()
            if upper_part in ("2D", "3D", "4DX", "IMAX"):
                format_str = upper_part
            elif upper_part in ("DOB", "SUB", "SUBTITULADA", "DOBLADA"):
                translation_type = part
            else:
                if not format_str:
                    format_str = part

        return format_str, translation_type

    @staticmethod
    def _parse_royal_time(time_text: str) -> datetime.time | None:
        """Parse time text like '04:30 p. m.' or '07:00 p.m.'."""
        time_text = time_text.strip().lower()
        # Replace non-breaking space (NBSP) with regular space, then remove all spaces and dots
        time_text = time_text.replace("\xa0", " ").replace(" ", "").replace(".", "")

        match = re.match(r"(\d{1,2}):(\d{2})(am|pm)", time_text)
        if match:
            hour = int(match.group(1))
            minute = int(match.group(2))
            period = match.group(3)

            if period == "pm" and hour != 12:
                hour += 12
            elif period == "am" and hour == 12:
                hour = 0

            try:
                return datetime.time(hour, minute)
            except ValueError:
                return None

        return parse_time_string(time_text)


class RoyalShowtimeSaver(MovieAndShowtimeSaverTemplate):
    """Scraper implementation for Royal Films theaters."""

    def __init__(
        self,
        scraper: RoyalScraperAndHTMLParser,
        tmdb_service: TMDBService,
        storage_service: SupabaseStorageService | None,
    ):
        super().__init__(
            tmdb_service=tmdb_service,
            storage_service=storage_service,
            source_name=SOURCE_NAME,
            scraper_type="royal",
            scraper_type_enum=MovieSourceUrl.ScraperType.ROYAL_FILMS,
            task_name=TASK_NAME,
        )
        self.scraper = scraper

    def _find_movies(self, theater: Theater) -> list[MovieInfo]:
        """Find all movies showing at the theater."""
        if not theater.download_source_url:
            logger.warning(f"No download_source_url for theater {theater.name}")
            return []

        html = self.scraper.download_theater_page_html(theater.download_source_url)
        movie_cards = self.scraper.parse_movies_from_theater_html(html)

        logger.info(f"Found {len(movie_cards)} movies at {theater.name}")

        return [
            MovieInfo(name=card.title, source_url=card.url)
            for card in movie_cards
        ]

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
        """Scrape showtimes for all movies at a theater."""
        all_showtimes: list[ShowtimeData] = []
        dates_to_delete: set[datetime.date] = set()

        for movie_info in movies_for_theater:
            movie = movies_cache.get(movie_info.source_url)
            if not movie:
                continue

            try:
                html = self.scraper.download_movie_page_html(movie_info.source_url)

                if self.scraper.has_no_showtimes_message(html):
                    logger.debug(f"No showtimes available for {movie_info.name} - skipping")
                    continue

                dates = self.scraper.parse_available_dates_from_movie_html(html)
                if not dates:
                    logger.warning(f"No dates found for movie {movie_info.name}")
                    continue

                for date in dates:
                    dates_to_delete.add(date)

                    showtimes = self.scraper.parse_showtimes_from_movie_html(
                        html, theater.name, date
                    )

                    for st in showtimes:
                        translation_type = normalize_translation_type(
                            st.translation_type,
                            task=TASK_NAME,
                            context={"theater": theater.name, "movie": movie_info.name},
                        )
                        all_showtimes.append(ShowtimeData(
                            movie=movie,
                            date=st.date,
                            time=st.time,
                            format=st.format,
                            translation_type=translation_type,
                            screen="",
                            source_url=movie_info.source_url,
                        ))

            except Exception as e:
                logger.error(f"Error processing movie {movie_info.name}: {e}")
                OperationalIssue.objects.create(
                    name="Movie Processing Error",
                    task=TASK_NAME,
                    error_message=str(e),
                    traceback=traceback.format_exc(),
                    context={
                        "theater": theater.name,
                        "movie": movie_info.name,
                        "url": movie_info.source_url,
                    },
                    severity=OperationalIssue.Severity.ERROR,
                )

        return self._save_showtimes_with_date_cleanup(theater, all_showtimes, dates_to_delete)

    def _save_showtimes_with_date_cleanup(
        self,
        theater: Theater,
        showtimes: list[ShowtimeData],
        dates: set[datetime.date],
    ) -> int:
        """Save showtimes atomically, deleting old ones for specified dates first."""
        with transaction.atomic():
            if dates:
                deleted_count = Showtime.objects.filter(
                    theater=theater,
                    start_date__in=dates,
                ).delete()[0]
                logger.info(f"Deleted {deleted_count} old showtimes for {theater.name}")

            showtime_objects = [
                Showtime(
                    theater=theater,
                    movie=st.movie,
                    start_date=st.date,
                    start_time=st.time,
                    format=st.format,
                    translation_type=st.translation_type,
                    screen=st.screen,
                    source_url=st.source_url,
                )
                for st in showtimes
            ]
            Showtime.objects.bulk_create(showtime_objects)
            logger.info(f"Saved {len(showtime_objects)} showtimes for {theater.name}")

        return len(showtime_objects)


@app.task
def royal_download_task() -> TaskReport:
    """Celery task to download Royal Films showtimes."""
    scraper = RoyalScraperAndHTMLParser()
    tmdb_service = TMDBService()
    storage_service = SupabaseStorageService.create_from_settings()

    saver = RoyalShowtimeSaver(scraper, tmdb_service, storage_service)
    report = saver.execute()
    report.print_report()
    return report
