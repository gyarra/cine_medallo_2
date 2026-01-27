"""
Cinemark Scraper Task

Celery task for scraping movie showtime data from Cinemark theaters.

The cartelera (movie list) is at: https://www.cinemark.com.co/ciudad/{city}/{theater_slug}
Individual movie pages are at: https://www.cinemark.com.co/{movie_slug}
"""

from __future__ import annotations

import datetime
import logging
import re
import traceback
from dataclasses import dataclass, field

from bs4 import BeautifulSoup, Tag

from config.celery_app import app
from movies_app.models import Movie, MovieSourceUrl, OperationalIssue, Theater
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.download_utilities import (
    BOGOTA_TZ,
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
    poster_url: str = ""


@dataclass
class CinemarkMovieMetadata:
    """Detailed movie info from movie detail page."""
    title: str
    original_title: str | None
    synopsis: str
    classification: str
    cast: list[str]
    poster_url: str


@dataclass
class CinemarkShowtime:
    """Showtime info extracted from movie detail page."""
    date: datetime.date
    time: datetime.time
    format: str
    translation_type: str
    seat_type: str


@dataclass
class CinemarkShowtimeBlock:
    """A block of showtimes with shared format/translation/seat info."""
    format: str
    translation_type: str
    seat_type: str
    times: list[datetime.time] = field(default_factory=list)


class CinemarkScraperAndHTMLParser:
    """Stateless class for fetching and parsing Cinemark web pages."""

    @staticmethod
    def download_cartelera_html(url: str) -> str:
        """Download theater cartelera page HTML."""
        return fetch_page_html(url, wait_selector="a[href*='cinemark.com.co/']", sleep_seconds_after_wait=2)

    @staticmethod
    def download_movie_detail_html(url: str) -> str:
        """Download movie detail page HTML."""
        return fetch_page_html(url, wait_selector=".sessions", sleep_seconds_after_wait=2)

    @staticmethod
    def parse_movies_from_cartelera_html(html_content: str, base_url: str = "https://www.cinemark.com.co") -> list[CinemarkMovieCard]:
        """Extract movie cards from theater cartelera page."""
        soup = BeautifulSoup(html_content, "lxml")

        movies: list[CinemarkMovieCard] = []
        seen_slugs: set[str] = set()

        # Find all links that match movie URL pattern
        links = soup.find_all("a", href=True)
        for link in links:
            href = str(link.get("href") or "")

            # Movie URLs are like https://www.cinemark.com.co/{movie-slug}
            # Skip non-movie URLs
            if not href.startswith(base_url):
                if href.startswith("/") and not any(skip in href for skip in ["/cartelera", "/cine-club", "/confiteria", "/promociones", "/ciudad", "/static"]):
                    href = base_url + href
                else:
                    continue

            # Extract slug from URL
            slug = CinemarkScraperAndHTMLParser._extract_slug_from_url(href)
            if not slug or slug in seen_slugs:
                continue

            # Skip non-movie pages
            skip_patterns = ["cartelera", "cine-club", "confiteria", "promociones", "ciudad", "formatos", "conocenos"]
            if any(pattern in slug for pattern in skip_patterns):
                continue

            seen_slugs.add(slug)

            # Try to get movie title from link text or img alt
            title = link.get_text(strip=True)
            if not title or title == "cargando":
                img = link.find("img")
                if img:
                    title = str(img.get("alt") or "")

            if not title or title == "cargando":
                # Use slug as fallback title
                title = slug.replace("-", " ").title()

            # Get poster URL if available
            poster_url = ""
            img = link.find("img")
            if img:
                src = str(img.get("src") or "")
                if src and "loading" not in src and "icon" not in src:
                    poster_url = src

            movies.append(CinemarkMovieCard(
                title=title,
                slug=slug,
                url=href,
                poster_url=poster_url,
            ))

        return movies

    @staticmethod
    def _extract_slug_from_url(url: str) -> str | None:
        """Extract movie slug from URL like https://www.cinemark.com.co/movie-slug."""
        match = re.search(r"cinemark\.com\.co/([^/?#]+)$", url)
        if match:
            return match.group(1)
        return None

    @staticmethod
    def parse_movie_metadata_from_detail_html(html_content: str) -> CinemarkMovieMetadata | None:
        """Extract movie metadata from detail page."""
        soup = BeautifulSoup(html_content, "lxml")

        # Find title from img alt in moviePoster section or breadcrumb
        title = ""
        poster_url = ""

        # Try to get from img with movie poster
        movie_poster = soup.find(class_="moviePoster")
        if movie_poster:
            imgs = movie_poster.find_all("img")
            for img in imgs:
                alt = str(img.get("alt") or "")
                src = str(img.get("src") or "")
                if alt and "loading" not in alt.lower():
                    title = alt
                    if src and "loading" not in src and "icon" not in src:
                        poster_url = src
                    break

        # Fallback: try information-movie section
        if not title:
            info_section = soup.find(class_="information-movie")
            if info_section:
                imgs = info_section.find_all("img")
                for img in imgs:
                    alt = str(img.get("alt") or "")
                    src = str(img.get("src") or "")
                    if alt and "loading" not in alt.lower():
                        title = alt
                        if not poster_url and src and "loading" not in src:
                            poster_url = src
                        break

        if not title:
            return None

        # Extract metadata from h4 + p pairs
        original_title: str | None = None
        synopsis = ""
        classification = ""
        cast: list[str] = []

        h4_elements = soup.find_all("h4")
        for h4 in h4_elements:
            header_text = h4.get_text(strip=True).lower()
            next_elem = h4.find_next_sibling("p")
            if not next_elem:
                continue
            content = next_elem.get_text(strip=True)

            if "título original" in header_text:
                original_title = content
            elif "reparto" in header_text:
                # Parse cast list
                cast = [actor.strip() for actor in content.split(",") if actor.strip()]
            elif "sinopsis" in header_text:
                synopsis = content
            elif "clasificación" in header_text:
                classification = content

        # Also check container-badge for classification
        if not classification:
            badge = soup.find(class_="container-badge")
            if badge:
                classification = badge.get_text(strip=True)

        return CinemarkMovieMetadata(
            title=title,
            original_title=original_title,
            synopsis=synopsis,
            classification=classification,
            cast=cast,
            poster_url=poster_url,
        )

    @staticmethod
    def parse_available_dates_from_detail_html(html_content: str) -> list[datetime.date]:
        """Extract available showtime dates from movie detail page."""
        soup = BeautifulSoup(html_content, "lxml")
        dates: list[datetime.date] = []

        week_days = soup.find_all(class_="week__day")
        for day_elem in week_days:
            # Find the date span (has week__date--small-font class)
            date_span = day_elem.find(class_="week__date--small-font")
            if not date_span:
                continue

            date_text = date_span.get_text(strip=True)
            parsed_date = CinemarkScraperAndHTMLParser._parse_date_string(date_text)
            if parsed_date:
                dates.append(parsed_date)

        return dates

    @staticmethod
    def _parse_date_string(date_text: str) -> datetime.date | None:
        """Parse date string like '27 ene. 2026' or '27 ene 2026'."""
        # Remove trailing period from month abbreviation
        date_text = date_text.replace(".", " ").strip()

        # Match pattern: day month year
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
    def get_selected_date_from_detail_html(html_content: str) -> datetime.date | None:
        """Get the currently selected date from the week selector."""
        soup = BeautifulSoup(html_content, "lxml")

        selected_day = soup.find(class_="week__day--selected")
        if not selected_day:
            return None

        date_span = selected_day.find(class_="week__date--small-font")
        if not date_span:
            return None

        date_text = date_span.get_text(strip=True)
        return CinemarkScraperAndHTMLParser._parse_date_string(date_text)

    @staticmethod
    def parse_showtimes_from_detail_html(
        html_content: str,
        theater_name: str,
        selected_date: datetime.date,
    ) -> list[CinemarkShowtime]:
        """Extract showtimes for a specific theater from movie detail page."""
        soup = BeautifulSoup(html_content, "lxml")
        showtimes: list[CinemarkShowtime] = []

        # Find all theater sections (ant-collapse-item)
        collapse_items = soup.find_all(class_="ant-collapse-item")

        for item in collapse_items:
            # Check if this is the right theater
            theater_name_elem = item.find(class_="theaters-name")
            if not theater_name_elem:
                continue

            accordion_theater_name = theater_name_elem.get_text(strip=True)
            if not CinemarkScraperAndHTMLParser._theater_names_match(accordion_theater_name, theater_name):
                continue

            # Find all showtime blocks in this theater
            showtime_containers = item.find_all(class_="theater-detail__container--principal")

            for container in showtime_containers:
                block = CinemarkScraperAndHTMLParser._parse_showtime_block(container)
                if not block:
                    continue

                for time in block.times:
                    showtimes.append(CinemarkShowtime(
                        date=selected_date,
                        time=time,
                        format=block.format,
                        translation_type=block.translation_type,
                        seat_type=block.seat_type,
                    ))

        return showtimes

    @staticmethod
    def _parse_showtime_block(container: Tag) -> CinemarkShowtimeBlock | None:
        """Parse a showtime block containing format, translation, seat type, and times."""
        header = container.find(class_="theaters-detail__header")
        if not header:
            return None

        # Extract format and translation type from formats__item spans
        format_items = header.find_all(class_="formats__item")
        format_str = ""
        translation_type = ""

        for i, item in enumerate(format_items):
            text = item.get_text(strip=True).lower()
            if i == 0:
                format_str = text.upper()  # e.g., "2D", "3D"
            elif i == 1:
                translation_type = text.capitalize()  # e.g., "Doblada", "Subtitulada"

        # Extract seat type (after "Sillas:" text)
        seat_type = ""
        item_div = header.find(class_="theaters-detail__item")
        if item_div:
            spans = item_div.find_all("span")
            found_sillas = False
            for span in spans:
                text = span.get_text(strip=True)
                if "Sillas:" in text:
                    found_sillas = True
                elif found_sillas and text:
                    seat_type = text.capitalize()
                    break

        # Extract times
        times: list[datetime.time] = []
        times_container = container.find(class_="theaters-detail__container")
        if times_container:
            time_buttons = times_container.find_all(class_="sessions__button--runtime")
            for btn in time_buttons:
                time_text = btn.get_text(strip=True)
                parsed_time = parse_time_string(time_text)
                if parsed_time:
                    times.append(parsed_time)

        if not times:
            return None

        return CinemarkShowtimeBlock(
            format=format_str or "2D",
            translation_type=translation_type or "Doblada",
            seat_type=seat_type or "General",
            times=times,
        )

    @staticmethod
    def _theater_names_match(accordion_name: str, target_name: str) -> bool:
        """Check if accordion theater name matches our target theater."""
        accordion_normalized = accordion_name.lower().strip()
        target_normalized = target_name.lower().strip()

        # Direct substring match
        if target_normalized in accordion_normalized:
            return True
        if accordion_normalized in target_normalized:
            return True

        # Word-based matching
        target_parts = target_normalized.split()
        accordion_parts = accordion_normalized.split()

        matches = sum(1 for part in target_parts if part in accordion_parts)
        return matches >= len(target_parts) // 2 + 1

    @staticmethod
    def generate_movie_source_url(slug: str) -> str:
        """Generate canonical movie URL for MovieSourceUrl storage."""
        return f"https://www.cinemark.com.co/{slug}"


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
        self._movie_cards_cache: dict[str, CinemarkMovieCard] = {}

    def _find_movies(self, theater: Theater) -> list[MovieInfo]:
        """Download cartelera and return list of movies."""
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

        html_content = self.scraper.download_cartelera_html(cartelera_url)
        movie_cards = self.scraper.parse_movies_from_cartelera_html(html_content)

        if not movie_cards:
            logger.warning(f"No movies found in cartelera for {theater.name}")
            OperationalIssue.objects.create(
                name="Cinemark No Movies Found",
                task=TASK_NAME,
                error_message=f"No movies found in cartelera for {theater.name}",
                context={"cartelera_url": cartelera_url},
                severity=OperationalIssue.Severity.WARNING,
            )
            return []

        logger.info(f"Found {len(movie_cards)} movies for {theater.name}")

        movies: list[MovieInfo] = []
        for card in movie_cards:
            source_url = self.scraper.generate_movie_source_url(card.slug)
            self._movie_cards_cache[source_url] = card
            movies.append(MovieInfo(name=card.title, source_url=source_url))

        return movies

    def _get_movie_metadata(self, movie_info: MovieInfo) -> MovieMetadata | None:
        """Download movie detail page and extract metadata."""
        card = self._movie_cards_cache.get(movie_info.source_url)
        if not card:
            logger.error(f"No movie card cached for {movie_info.source_url}")
            return None

        html_content = self.scraper.download_movie_detail_html(card.url)
        cinemark_meta = self.scraper.parse_movie_metadata_from_detail_html(html_content)

        if not cinemark_meta:
            logger.warning(f"Could not extract metadata for '{movie_info.name}'")
            return None

        return MovieMetadata(
            genre="",
            duration_minutes=None,
            classification=cinemark_meta.classification,
            director="",
            actors=cinemark_meta.cast,
            original_title=cinemark_meta.original_title,
            release_date=None,
            release_year=None,
            trailer_url=None,
        )

    def _process_showtimes_for_theater(
        self,
        theater: Theater,
        movies_for_theater: list[MovieInfo],
        movies_cache: dict[str, Movie | None],
    ) -> int:
        """Scrape showtimes and save them for a theater."""
        logger.info(f"Processing Cinemark theater: {theater.name}")

        all_showtimes: list[ShowtimeData] = []

        for movie_info in movies_for_theater:
            card = self._movie_cards_cache.get(movie_info.source_url)
            if not card:
                continue

            movie = movies_cache.get(movie_info.source_url)
            if not movie:
                logger.debug(f"Skipping showtimes for unfindable movie: {card.title}")
                continue

            try:
                showtimes = self._collect_showtimes_for_movie(card, movie, theater)
                all_showtimes.extend(showtimes)
            except Exception as e:
                logger.error(f"Failed to process movie {card.title}: {e}")
                OperationalIssue.objects.create(
                    name="Cinemark Movie Processing Failed",
                    task=TASK_NAME,
                    error_message=str(e),
                    traceback=traceback.format_exc(),
                    context={"movie_title": card.title, "movie_url": card.url},
                    severity=OperationalIssue.Severity.WARNING,
                )

        return self._save_showtimes_for_theater(theater, all_showtimes)

    def _collect_showtimes_for_movie(
        self,
        card: CinemarkMovieCard,
        movie: Movie,
        theater: Theater,
    ) -> list[ShowtimeData]:
        """Download movie detail page and collect showtimes."""
        logger.info(f"Processing movie: {card.title}")

        html_content = self.scraper.download_movie_detail_html(card.url)

        # Get available dates
        available_dates = self.scraper.parse_available_dates_from_detail_html(html_content)

        # If no dates found, use the selected date or today
        if not available_dates:
            selected_date = self.scraper.get_selected_date_from_detail_html(html_content)
            if selected_date:
                available_dates = [selected_date]
            else:
                today = datetime.datetime.now(BOGOTA_TZ).date()
                available_dates = [today]

        showtimes: list[ShowtimeData] = []

        for date in available_dates:
            cinemark_showtimes = self.scraper.parse_showtimes_from_detail_html(
                html_content, theater.name, date
            )

            for st in cinemark_showtimes:
                translation_type = normalize_translation_type(
                    st.translation_type,
                    task=TASK_NAME,
                    context={"theater": theater.name, "movie": movie.title_es},
                )
                showtimes.append(ShowtimeData(
                    movie=movie,
                    date=st.date,
                    time=st.time,
                    format=st.format,
                    translation_type=translation_type,
                    screen=st.seat_type,
                    source_url=card.url,
                ))

        return showtimes


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
