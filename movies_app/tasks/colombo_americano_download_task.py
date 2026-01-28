"""
Colombo Americano Scraper Task

Celery task for scraping movie showtime data from
Centro Colombo Americano de Medellín.

The weekly schedule is at: https://www.colombomedellin.edu.co/programacion-por-salas/
Individual movie pages are at: https://www.colombomedellin.edu.co/peliculas/<slug>/

This is a simple HTML-only scraper (no JavaScript rendering required).
"""

from __future__ import annotations

import datetime
import logging
import re
import traceback
import urllib.request
from dataclasses import dataclass

from bs4 import BeautifulSoup
from django.db import transaction

from config.celery_app import app
from movies_app.models import Movie, MovieSourceUrl, OperationalIssue, Showtime, Theater
from movies_app.services.movie_lookup_result import MovieLookupResult
from movies_app.services.movie_lookup_service import MovieLookupService
from movies_app.services.supabase_storage_service import SupabaseStorageService
from movies_app.services.tmdb_service import TMDBService
from movies_app.tasks.download_utilities import (
    BOGOTA_TZ,
    MovieMetadata,
    TaskReport,
    parse_time_string,
)

logger = logging.getLogger(__name__)

COLOMBO_CINE_URL = "https://www.colombomedellin.edu.co/programacion-por-salas/"
SOURCE_NAME = "colombo_americano"


@dataclass
class ColomboShowtime:
    movie_title: str
    movie_url: str
    date: datetime.date
    time: datetime.time


@dataclass
class ColomboMovieMetadata:
    title: str
    director: str
    duration_minutes: int | None
    year: int | None
    country: str
    synopsis: str
    poster_url: str
    trailer_url: str


class ColomboAmericanoScraperAndHTMLParser:
    """Stateless class for fetching and parsing Colombo Americano web pages."""

    @staticmethod
    def download_weekly_schedule() -> str:
        request = urllib.request.Request(
            COLOMBO_CINE_URL,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")

    @staticmethod
    def download_individual_movie_html(url: str) -> str:
        request = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
        )
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read().decode("utf-8")

    @staticmethod
    def parse_showtimes_from_weekly_schedule_html(html_content: str) -> list[ColomboShowtime]:
        soup = BeautifulSoup(html_content, "lxml")

        showtimes: list[ColomboShowtime] = []
        today = datetime.datetime.now(BOGOTA_TZ).date()
        reference_year = today.year

        movie_items = soup.find_all("div", class_="jet-listing-grid__item")

        for item in movie_items:
            overlay_wrap = item.find("div", class_="jet-engine-listing-overlay-wrap")
            if not overlay_wrap:
                continue

            movie_url = overlay_wrap.get("data-url")
            if not movie_url or not isinstance(movie_url, str):
                continue

            # Find the title element - must be in a div with data-widget_type="heading.default"
            # but NOT in a div with "elementor-widget__width-auto" class (those are tags like "2X1")
            title_containers = item.find_all("div", class_="elementor-element", attrs={"data-widget_type": "heading.default"})
            title_elem = None
            for container in title_containers:
                container_classes = container.get("class") or []
                if "elementor-widget__width-auto" not in container_classes:
                    title_elem = container.find("h2", class_="elementor-heading-title")
                    if title_elem:
                        break
            if not title_elem:
                continue
            movie_title = ColomboAmericanoScraperAndHTMLParser._normalize_whitespace(title_elem.get_text())

            dynamic_fields = item.find_all("div", class_="jet-listing-dynamic-field__content")
            if len(dynamic_fields) < 2:
                continue

            date_text = ColomboAmericanoScraperAndHTMLParser._normalize_whitespace(dynamic_fields[0].get_text())
            time_text = ColomboAmericanoScraperAndHTMLParser._normalize_whitespace(dynamic_fields[1].get_text())

            parsed_date = ColomboAmericanoScraperAndHTMLParser._parse_date_string(date_text, reference_year)
            if not parsed_date:
                logger.warning(f"Could not parse date: {date_text}")
                continue

            delta_days = (parsed_date - today).days
            if delta_days > 180:
                parsed_date = parsed_date.replace(year=parsed_date.year - 1)
            elif delta_days < -180:
                parsed_date = parsed_date.replace(year=parsed_date.year + 1)

            parsed_time = parse_time_string(time_text)
            if not parsed_time:
                logger.warning(f"Could not parse time: {time_text}")
                OperationalIssue.objects.create(
                    name="Time Parse Failed",
                    task="colombo_americano_download_task",
                    error_message=f"Could not parse time string: '{time_text}'",
                    context={"movie": movie_title, "date": str(parsed_date)},
                    severity=OperationalIssue.Severity.WARNING,
                )
                continue

            showtimes.append(ColomboShowtime(
                movie_title=movie_title,
                movie_url=movie_url,
                date=parsed_date,
                time=parsed_time,
            ))

        return showtimes

    @staticmethod
    def parse_movie_meta_from_movie_html(html_content: str) -> ColomboMovieMetadata | None:
        soup = BeautifulSoup(html_content, "lxml")

        title_elem = soup.find("h2", class_="elementor-heading-title")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)

        director = ""
        duration_minutes: int | None = None
        year: int | None = None
        country = ""
        synopsis = ""
        poster_url = ""
        trailer_url = ""

        dynamic_fields = soup.find_all("div", class_="jet-listing-dynamic-field__content")
        for field in dynamic_fields:
            text = field.get_text(strip=True)

            if text.startswith("Director:"):
                director = text.replace("Director:", "").strip()
            elif text.startswith("Duración:"):
                duration_match = re.search(r"(\d+)\s*min", text, re.IGNORECASE)
                if duration_match:
                    duration_minutes = int(duration_match.group(1))
            elif text.startswith("País:"):
                country = text.replace("País:", "").strip()
            elif text.startswith("Año:"):
                year_match = re.search(r"(\d{4})", text)
                if year_match:
                    year = int(year_match.group(1))

        content_div = soup.find("div", class_="elementor-widget-container")
        if content_div:
            paragraphs = content_div.find_all("p")
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 100 and not text.startswith("Director:"):
                    synopsis = text
                    break

        featured_img = soup.find("img", class_="attachment-full")
        if featured_img and featured_img.get("src"):
            poster_url = str(featured_img["src"])

        iframe = soup.find("iframe")
        if iframe and iframe.get("src"):
            src = str(iframe["src"])
            if "youtube" in src:
                video_match = re.search(r"embed/([a-zA-Z0-9_-]+)", src)
                if video_match:
                    trailer_url = f"https://www.youtube.com/watch?v={video_match.group(1)}"

        return ColomboMovieMetadata(
            title=title,
            director=director,
            duration_minutes=duration_minutes,
            year=year,
            country=country,
            synopsis=synopsis,
            poster_url=poster_url,
            trailer_url=trailer_url,
        )

    @staticmethod
    def _normalize_whitespace(text: str) -> str:
        """Collapse multiple whitespace characters into a single space."""
        return " ".join(text.split())

    @staticmethod
    def _parse_date_string(date_str: str, reference_year: int) -> datetime.date | None:
        """
        Parse date strings like 'enero 27', 'febrero 1', etc.
        """
        month_map = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
        }

        for month_name, month_num in month_map.items():
            if month_name in date_str.lower():
                day_match = re.search(r"(\d{1,2})", date_str)
                if day_match:
                    day = int(day_match.group(1))
                    try:
                        return datetime.date(reference_year, month_num, day)
                    except ValueError:
                        return None
                break

        return None


class ColomboAmericanoShowtimeSaver:
    """Coordinates scraping and saves movies/showtimes to the database."""

    def __init__(
        self,
        scraper: ColomboAmericanoScraperAndHTMLParser,
        tmdb_service: TMDBService,
        storage_service: SupabaseStorageService | None,
    ):
        self.scraper = scraper
        self.lookup_service = MovieLookupService(tmdb_service, storage_service, SOURCE_NAME)
        self.theater = Theater.objects.get(slug="colombo-americano-medellin")
        self.processed_movies: dict[str, Movie | None] = {}
        self.tmdb_calls = 0
        self.new_movies: list[str] = []

    def execute(self) -> TaskReport:
        html_content = self.scraper.download_weekly_schedule()

        showtimes = self.scraper.parse_showtimes_from_weekly_schedule_html(html_content)
        logger.info(f"Extracted {len(showtimes)} showtimes from Colombo Americano schedule\n\n")

        if not showtimes:
            logger.warning("No showtimes extracted from Colombo Americano schedule")
            return TaskReport(total_showtimes=0, tmdb_calls=0, new_movies=[])

        self._process_movies(showtimes)

        total_showtimes = self._save_showtimes(showtimes)

        return TaskReport(
            total_showtimes=total_showtimes,
            tmdb_calls=self.tmdb_calls,
            new_movies=self.new_movies,
        )

    def _process_movies(self, showtimes: list[ColomboShowtime]) -> None:
        unique_movies: dict[str, tuple[str, str]] = {}

        for showtime in showtimes:
            if showtime.movie_url not in unique_movies:
                unique_movies[showtime.movie_url] = (showtime.movie_title, showtime.movie_url)

        for movie_url, (movie_title, _) in unique_movies.items():
            result = self._get_or_create_movie(movie_title, movie_url)
            self.processed_movies[movie_url] = result.movie

            if result.tmdb_called:
                self.tmdb_calls += 1
            if result.is_new and result.movie:
                self.new_movies.append(result.movie.title_es)

    def _get_or_create_movie(
        self,
        movie_title: str,
        movie_url: str,
    ) -> MovieLookupResult:
        existing_movie = MovieSourceUrl.get_movie_for_source_url(
            url=movie_url,
            scraper_type=MovieSourceUrl.ScraperType.COLOMBO_AMERICANO,
        )
        if existing_movie:
            return MovieLookupResult(movie=existing_movie, is_new=False, tmdb_called=False)

        metadata = self._fetch_movie_metadata(movie_url, movie_title)

        return self.lookup_service.get_or_create_movie(
            movie_name=movie_title,
            source_url=movie_url,
            scraper_type=MovieSourceUrl.ScraperType.COLOMBO_AMERICANO,
            metadata=metadata,
        )

    def _fetch_movie_metadata(self, movie_url: str, movie_title: str) -> MovieMetadata | None:
        try:
            html_content = self.scraper.download_individual_movie_html(movie_url)
            colombo_meta = self.scraper.parse_movie_meta_from_movie_html(html_content)

            if not colombo_meta:
                logger.warning(f"Could not extract metadata from Colombo page for '{movie_title}'")
                return None

            return MovieMetadata(
                genre="",
                duration_minutes=colombo_meta.duration_minutes,
                classification="",
                director=colombo_meta.director,
                actors=[],
                original_title=None,
                release_date=None,
                release_year=colombo_meta.year,
                trailer_url=colombo_meta.trailer_url or None,
            )

        except Exception as e:
            logger.warning(f"Failed to scrape Colombo movie page for '{movie_title}': {e}")
            OperationalIssue.objects.create(
                name="Colombo Movie Page Scrape Failed",
                task="_fetch_movie_metadata",
                error_message=f"Failed to scrape Colombo movie page for '{movie_title}': {e}",
                context={"movie_title": movie_title, "movie_url": movie_url},
                severity=OperationalIssue.Severity.WARNING,
            )
            return None

    def _save_showtimes(self, showtimes: list[ColomboShowtime]) -> int:
        showtimes_by_date: dict[datetime.date, list[ColomboShowtime]] = {}
        for showtime in showtimes:
            if showtime.date not in showtimes_by_date:
                showtimes_by_date[showtime.date] = []
            showtimes_by_date[showtime.date].append(showtime)

        total_showtimes = 0
        for date in sorted(showtimes_by_date.keys()):
            showtimes_saved = self._save_showtimes_for_date(date, showtimes_by_date[date])
            total_showtimes += showtimes_saved

        logger.info(f"Saved {total_showtimes} total showtimes for Colombo Americano")
        return total_showtimes

    @transaction.atomic
    def _save_showtimes_for_date(
        self,
        date: datetime.date,
        showtimes_for_date: list[ColomboShowtime],
    ) -> int:
        deleted_count, _ = Showtime.objects.filter(
            theater=self.theater,
            start_date=date,
        ).delete()
        if deleted_count:
            logger.info(f"Deleted {deleted_count} existing showtimes for {date}")

        showtimes_saved = 0

        for showtime in showtimes_for_date:
            movie = self.processed_movies.get(showtime.movie_url)

            if not movie:
                logger.debug(f"Skipping showtime for unfindable movie: {showtime.movie_title}")
                continue

            Showtime.objects.create(
                theater=self.theater,
                movie=movie,
                start_date=showtime.date,
                start_time=showtime.time,
                format="",
                translation_type="",
                screen="",
                source_url=self.theater.download_source_url,
            )
            showtimes_saved += 1
            logger.debug(f"Created showtime: {movie.title_es} at {showtime.date} {showtime.time}")

        logger.info(f"Saved {showtimes_saved} showtimes for Colombo Americano on {date}")
        return showtimes_saved


@app.task
def colombo_americano_download_task():
    logger.info("Starting colombo_americano_download_task")

    try:
        scraper = ColomboAmericanoScraperAndHTMLParser()
        tmdb_service = TMDBService()
        storage_service = SupabaseStorageService.create_from_settings()
        if not storage_service:
            raise RuntimeError("Failed to create storage service")

        saver = ColomboAmericanoShowtimeSaver(scraper, tmdb_service, storage_service)
        report = saver.execute()
        report.print_report()
        return report

    except Exception as e:
        logger.error(f"Failed Colombo Americano download task: {e}")
        OperationalIssue.objects.create(
            name="Colombo Americano Download Task Failed",
            task="colombo_americano_download_task",
            error_message=str(e),
            traceback=traceback.format_exc(),
            context={"url": COLOMBO_CINE_URL},
            severity=OperationalIssue.Severity.ERROR,
        )
        raise
