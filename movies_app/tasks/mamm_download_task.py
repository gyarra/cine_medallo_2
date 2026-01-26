"""
MAMM (elmamm.org) Scraper Task

Celery task for scraping movie showtime data from
Museo de Arte Moderno de Medellín (MAMM).

The weekly schedule is at: https://www.elmamm.org/cine/#semana
Individual movie pages are at: https://www.elmamm.org/producto/<slug>/
"""

from __future__ import annotations

import datetime
import logging
import re
import traceback
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
    SPANISH_MONTHS_ABBREVIATIONS,
    MovieMetadata,
    TaskReport,
    fetch_page_html,
    parse_time_string,
)

logger = logging.getLogger(__name__)

MAMM_CINE_URL = "https://www.elmamm.org/cine/"
SOURCE_NAME = "mamm"


@dataclass
class MAMMShowtime:
    movie_title: str
    movie_url: str | None
    date: datetime.date
    time: datetime.time
    special_label: str


@dataclass
class MAMMMovieMetadata:
    title: str
    age_rating: str
    duration_minutes: int | None
    director: str
    year: int | None
    country: str
    synopsis: str
    poster_url: str
    trailer_url: str


class MAMMScraperAndHTMLParser:
    """Stateless class for fetching and parsing MAMM web pages."""

    @staticmethod
    def download_weekly_schedule() -> str:
        return fetch_page_html(MAMM_CINE_URL)

    @staticmethod
    def download_individual_movie_html(url: str) -> str:
        return fetch_page_html(url)

    @staticmethod
    def parse_showtimes_from_weekly_schedule_html(html_content: str) -> list[MAMMShowtime]:
        soup = BeautifulSoup(html_content, "lxml")

        schedule_section = soup.find("section", class_="schedule-week")
        if not schedule_section:
            logger.warning("Could not find schedule-week section in MAMM HTML")
            return []

        showtimes: list[MAMMShowtime] = []
        today = datetime.datetime.now(BOGOTA_TZ).date()
        reference_year = today.year

        all_columns = schedule_section.find_all("div", class_="col")
        columns = [col for col in all_columns if "past-day" not in (col.get("class") or [])]

        for col in columns:
            day_div = col.find("div", class_="day")
            if not day_div:
                continue

            day_text_elem = day_div.find("p", class_="small")
            if not day_text_elem:
                continue

            day_text = day_text_elem.get_text(strip=True)
            parsed_date = MAMMScraperAndHTMLParser._parse_date_string(day_text, reference_year)

            if not parsed_date:
                logger.warning(f"Could not parse date: {day_text}")
                continue

            delta_days = (parsed_date - today).days
            if delta_days > 180:
                parsed_date = parsed_date.replace(year=parsed_date.year - 1)
            elif delta_days < -180:
                parsed_date = parsed_date.replace(year=parsed_date.year + 1)

            cards = col.find_all("div", class_="card")

            for card in cards:
                anchor = card.find("a")
                if not anchor:
                    continue

                time_elem = anchor.find("p", class_="small")
                title_elem = anchor.find("h3")

                if not time_elem or not title_elem:
                    continue

                time_text = time_elem.get_text(strip=True)
                movie_title = title_elem.get_text(strip=True)

                parsed_time = parse_time_string(time_text)
                if not parsed_time:
                    logger.warning(f"Could not parse time: {time_text}")
                    OperationalIssue.objects.create(
                        name="Time Parse Failed",
                        task="mamm_download_task",
                        error_message=f"Could not parse time string: '{time_text}'",
                        context={"movie": movie_title, "date": str(parsed_date)},
                        severity=OperationalIssue.Severity.WARNING,
                    )
                    continue

                movie_url: str | None = None
                href = anchor.get("href")
                if href and isinstance(href, str) and href.startswith("http"):
                    movie_url = href

                special_label = ""
                ciclo_span = card.find("span", class_="ciclo")
                if ciclo_span:
                    special_label = ciclo_span.get_text(strip=True)

                showtimes.append(MAMMShowtime(
                    movie_title=movie_title,
                    movie_url=movie_url,
                    date=parsed_date,
                    time=parsed_time,
                    special_label=special_label,
                ))

        return showtimes

    @staticmethod
    def parse_movie_meta_from_movie_html(html_content: str) -> MAMMMovieMetadata | None:
        soup = BeautifulSoup(html_content, "lxml")

        title_elem = soup.find("h1", class_="product_title")
        if not title_elem:
            return None

        title = title_elem.get_text(strip=True)

        age_rating = ""
        duration_minutes: int | None = None
        director = ""
        year: int | None = None
        country = ""
        synopsis = ""
        poster_url = ""
        trailer_url = ""

        short_desc = soup.find("div", class_="woocommerce-product-details__short-description")
        if short_desc:
            paragraphs = short_desc.find_all("p")
            for p in paragraphs:
                text = p.get_text(strip=True)

                if "|" in text and "min" in text.lower():
                    parts = text.split("|")
                    if len(parts) >= 1:
                        age_rating = parts[0].strip()
                    if len(parts) >= 2:
                        duration_match = re.search(r"(\d+)\s*min", parts[1], re.IGNORECASE)
                        if duration_match:
                            duration_minutes = int(duration_match.group(1))

                elif text.lower().startswith("director:"):
                    director = text.replace("Director:", "").replace("director:", "").strip()

                elif re.match(r"^\d{4}\s*\|", text):
                    parts = text.split("|")
                    if len(parts) >= 1:
                        year_match = re.match(r"(\d{4})", parts[0].strip())
                        if year_match:
                            year = int(year_match.group(1))
                    if len(parts) >= 2:
                        country = parts[1].strip()

                elif not synopsis and len(text) > 50:
                    synopsis = text

        gallery_img = soup.find("div", class_="woocommerce-product-gallery__image")
        if gallery_img:
            img = gallery_img.find("img")
            if img and img.get("src"):
                poster_url = str(img["src"])

        description_tab = soup.find("div", id="tab-description")
        if description_tab:
            iframe = description_tab.find("iframe")
            if iframe and iframe.get("src"):
                src = str(iframe["src"])
                if "youtube" in src:
                    video_match = re.search(r"embed/([a-zA-Z0-9_-]+)", src)
                    if video_match:
                        trailer_url = f"https://www.youtube.com/watch?v={video_match.group(1)}"

        return MAMMMovieMetadata(
            title=title,
            age_rating=age_rating,
            duration_minutes=duration_minutes,
            director=director,
            year=year,
            country=country,
            synopsis=synopsis,
            poster_url=poster_url,
            trailer_url=trailer_url,
        )

    @staticmethod
    def _parse_date_string(date_str: str, reference_year: int) -> datetime.date | None:
        match = re.search(r"(\d{1,2})\s+(\w{3})", date_str, re.IGNORECASE)
        if not match:
            return None

        day = int(match.group(1))
        month_abbr = match.group(2).lower()
        month = SPANISH_MONTHS_ABBREVIATIONS.get(month_abbr)

        if not month:
            return None

        try:
            return datetime.date(reference_year, month, day)
        except ValueError:
            return None


class MAMMShowtimeSaver:
    """Coordinates scraping and saves movies/showtimes to the database."""

    def __init__(
        self,
        scraper: MAMMScraperAndHTMLParser,
        tmdb_service: TMDBService,
        storage_service: SupabaseStorageService | None,
    ):
        self.scraper = scraper
        self.lookup_service = MovieLookupService(tmdb_service, storage_service, SOURCE_NAME)
        self.theater = Theater.objects.get(slug="museo-de-arte-moderno-de-medellin")
        self.processed_movies: dict[str, Movie | None] = {}
        self.tmdb_calls = 0
        self.new_movies: list[str] = []

    def execute(self) -> TaskReport:
        html_content = self.scraper.download_weekly_schedule()

        showtimes = self.scraper.parse_showtimes_from_weekly_schedule_html(html_content)
        logger.info(f"Extracted {len(showtimes)} showtimes from MAMM schedule\n\n")

        if not showtimes:
            logger.warning("No showtimes extracted from MAMM schedule")
            return TaskReport(total_showtimes=0, tmdb_calls=0, new_movies=[])

        self._process_movies(showtimes)

        total_showtimes = self._save_showtimes(showtimes)

        return TaskReport(
            total_showtimes=total_showtimes,
            tmdb_calls=self.tmdb_calls,
            new_movies=self.new_movies,
        )

    def _process_movies(self, showtimes: list[MAMMShowtime]) -> None:
        unique_movies: dict[str, tuple[str, str | None]] = {}

        for showtime in showtimes:
            cache_key = showtime.movie_url or showtime.movie_title
            if cache_key not in unique_movies:
                unique_movies[cache_key] = (showtime.movie_title, showtime.movie_url)

        for cache_key, (movie_title, movie_url) in unique_movies.items():
            result = self._get_or_create_movie(movie_title, movie_url)
            self.processed_movies[cache_key] = result.movie

            if result.tmdb_called:
                self.tmdb_calls += 1
            if result.is_new and result.movie:
                self.new_movies.append(result.movie.title_es)

    def _get_or_create_movie(
        self,
        movie_title: str,
        movie_url: str | None,
    ) -> MovieLookupResult:
        if not movie_url:
            logger.warning(f"No movie URL for '{movie_title}', cannot look up movie")
            OperationalIssue.objects.create(
                name="MAMM Missing Movie URL",
                task="mamm_download_task",
                error_message=f"No movie URL extracted for '{movie_title}'",
                context={"movie_title": movie_title},
                severity=OperationalIssue.Severity.WARNING,
            )
            return MovieLookupResult(movie=None, is_new=False, tmdb_called=False)

        existing_movie = MovieSourceUrl.get_movie_for_source_url(
            url=movie_url,
            scraper_type=MovieSourceUrl.ScraperType.MAMM,
        )
        if existing_movie:
            return MovieLookupResult(movie=existing_movie, is_new=False, tmdb_called=False)

        metadata = self._fetch_movie_metadata(movie_url, movie_title)

        return self.lookup_service.get_or_create_movie(
            movie_name=movie_title,
            source_url=movie_url,
            scraper_type=MovieSourceUrl.ScraperType.MAMM,
            metadata=metadata,
        )

    def _fetch_movie_metadata(self, movie_url: str, movie_title: str) -> MovieMetadata | None:
        try:
            html_content = self.scraper.download_individual_movie_html(movie_url)
            mamm_meta = self.scraper.parse_movie_meta_from_movie_html(html_content)

            if not mamm_meta:
                logger.warning(f"Could not extract metadata from MAMM page for '{movie_title}'")
                return None

            return MovieMetadata(
                genre="",
                duration_minutes=mamm_meta.duration_minutes,
                classification=mamm_meta.age_rating,
                director=mamm_meta.director,
                actors=[],
                original_title=None,
                release_date=None,
                release_year=mamm_meta.year,
                trailer_url=mamm_meta.trailer_url or None,
            )

        except Exception as e:
            logger.warning(f"Failed to scrape MAMM movie page for '{movie_title}': {e}")
            OperationalIssue.objects.create(
                name="MAMM Movie Page Scrape Failed",
                task="_fetch_movie_metadata",
                error_message=f"Failed to scrape MAMM movie page for '{movie_title}': {e}",
                context={"movie_title": movie_title, "movie_url": movie_url},
                severity=OperationalIssue.Severity.WARNING,
            )
            return None

    def _save_showtimes(self, showtimes: list[MAMMShowtime]) -> int:
        showtimes_by_date: dict[datetime.date, list[MAMMShowtime]] = {}
        for showtime in showtimes:
            if showtime.date not in showtimes_by_date:
                showtimes_by_date[showtime.date] = []
            showtimes_by_date[showtime.date].append(showtime)

        total_showtimes = 0
        for date in sorted(showtimes_by_date.keys()):
            showtimes_saved = self._save_showtimes_for_date(date, showtimes_by_date[date])
            total_showtimes += showtimes_saved

        logger.info(f"Saved {total_showtimes} total showtimes for MAMM")
        return total_showtimes

    @transaction.atomic
    def _save_showtimes_for_date(
        self,
        date: datetime.date,
        showtimes_for_date: list[MAMMShowtime],
    ) -> int:
        deleted_count, _ = Showtime.objects.filter(
            theater=self.theater,
            start_date=date,
        ).delete()
        if deleted_count:
            logger.info(f"Deleted {deleted_count} existing showtimes for {date}")

        showtimes_saved = 0

        for showtime in showtimes_for_date:
            cache_key = showtime.movie_url or showtime.movie_title
            movie = self.processed_movies.get(cache_key)

            if not movie:
                logger.debug(f"Skipping showtime for unfindable movie: {showtime.movie_title}")
                continue

            Showtime.objects.create(
                theater=self.theater,
                movie=movie,
                start_date=showtime.date,
                start_time=showtime.time,
                format=showtime.special_label,
                translation_type="",
                screen="",
                source_url=showtime.movie_url or MAMM_CINE_URL,
            )
            showtimes_saved += 1
            logger.debug(f"Created showtime: {movie.title_es} at {showtime.date} {showtime.time}")

        logger.info(f"Saved {showtimes_saved} showtimes for MAMM on {date}")
        return showtimes_saved


@app.task
def mamm_download_task():
    logger.info("Starting mamm_download_task")

    try:
        scraper = MAMMScraperAndHTMLParser()
        tmdb_service = TMDBService()
        storage_service = SupabaseStorageService.create_from_settings()
        if not storage_service:
            raise RuntimeError("Failed to create storage service")

        saver = MAMMShowtimeSaver(scraper, tmdb_service, storage_service)
        report = saver.execute()
        report.print_report()
        return report

    except Exception as e:
        logger.error(f"Failed MAMM download task: {e}")
        OperationalIssue.objects.create(
            name="MAMM Download Task Failed",
            task="mamm_download_task",
            error_message=str(e),
            traceback=traceback.format_exc(),
            context={"url": MAMM_CINE_URL},
            severity=OperationalIssue.Severity.ERROR,
        )
        raise
