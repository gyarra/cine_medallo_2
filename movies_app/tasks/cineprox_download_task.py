"""
Cineprox (formerly Procinal) Scraper Task

Celery task for scraping movie showtime data from Cineprox theaters.

The cartelera (movie list) is at: https://www.cineprox.com/cartelera/{city}/{theater_slug}
Individual movie pages are at: https://www.cineprox.com/detalle-pelicula/{movie_id}-{movie_slug}?idCiudad={city_id}&idTeatro={theater_id}
"""

from __future__ import annotations

import datetime
import logging
import re
import traceback
from dataclasses import dataclass
from typing import TYPE_CHECKING
from urllib.parse import urlencode

from bs4 import BeautifulSoup
from django.db import transaction
from django.utils.text import slugify

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
    normalize_translation_type,
    parse_time_string,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

SOURCE_NAME = "cineprox"


@dataclass
class CineproxMovieCard:
    movie_id: str
    title: str
    slug: str
    poster_url: str
    category: str


@dataclass
class CineproxMovieMetadata:
    title: str
    original_title: str | None
    synopsis: str
    classification: str
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
    format: str
    translation_type: str
    room_type: str
    price: str | None


class CineproxScraperAndHTMLParser:
    """Stateless class for fetching and parsing Cineprox web pages."""

    @staticmethod
    def download_cartelera_html(url: str) -> str:
        return fetch_page_html(url, wait_selector="div#grid", sleep_seconds_after_wait=1)

    @staticmethod
    def download_movie_detail_html(url: str) -> str:
        return fetch_page_html(url, wait_selector="section.pelicula", sleep_seconds_after_wait=1)

    @staticmethod
    def parse_movies_from_cartelera_html(html_content: str) -> list[CineproxMovieCard]:
        soup = BeautifulSoup(html_content, "lxml")

        grid_div = soup.find("div", id="grid")
        if not grid_div:
            logger.warning("Could not find div#grid in Cineprox cartelera HTML")
            return []

        movies: list[CineproxMovieCard] = []
        movie_cards = grid_div.find_all("div", attrs={"data-testid": True})

        for card in movie_cards:
            testid = card.get("data-testid", "")
            if not isinstance(testid, str) or not testid.startswith("movie-card-"):
                continue

            movie_id = testid.replace("movie-card-", "")

            class_attr = card.get("class")
            classes = list(class_attr) if class_attr else []
            category = CineproxScraperAndHTMLParser._extract_category_from_classes(classes)

            title_elem = card.find("p", class_="card-text")
            if not title_elem:
                continue
            title = title_elem.get_text(strip=True)

            img_elem = card.find("img", class_="card-img-top")
            poster_url = ""
            if img_elem and img_elem.get("src"):
                poster_url = str(img_elem["src"])

            slug = slugify(title)

            movies.append(CineproxMovieCard(
                movie_id=movie_id,
                title=title,
                slug=slug,
                poster_url=poster_url,
                category=category,
            ))

        return movies

    @staticmethod
    def _extract_category_from_classes(classes: list[str]) -> str:
        category_map = ["preventa", "estrenos", "cartelera", "pronto"]
        for cls in classes:
            if cls in category_map:
                return cls
        return ""

    @staticmethod
    def parse_movie_metadata_from_detail_html(html_content: str) -> CineproxMovieMetadata | None:
        soup = BeautifulSoup(html_content, "lxml")

        pelicula_section = soup.find("section", class_="pelicula")
        if not pelicula_section:
            return None

        title = ""
        original_title: str | None = None
        synopsis = ""
        classification = ""
        duration_minutes: int | None = None
        genre = ""
        release_date: datetime.date | None = None
        country = ""
        director = ""
        actors: list[str] = []
        poster_url = ""

        info_pelicula = pelicula_section.find("div", class_="InfoPelicula")
        if info_pelicula:
            title_elem = info_pelicula.find("h2")
            if title_elem:
                title = title_elem.get_text(strip=True)

            h5_elems = info_pelicula.find_all("h5")
            for h5 in h5_elems:
                text = h5.get_text(strip=True)
                if "Nombre original:" in text:
                    original_title = text.replace("Nombre original:", "").strip()

            synopsis_header = info_pelicula.find("h6")
            if synopsis_header:
                next_p = synopsis_header.find_next_sibling("p")
                if next_p:
                    synopsis = next_p.get_text(strip=True)

        info1_peli = pelicula_section.find("div", class_="Info1Peli")
        if info1_peli:
            li_elems = info1_peli.find_all("li")
            for li in li_elems:
                text = li.get_text(strip=True)
                if text.startswith("Clasificación:"):
                    classification = text.replace("Clasificación:", "").strip()
                elif text.startswith("Duración:"):
                    duration_str = text.replace("Duración:", "").strip()
                    duration_match = re.search(r"(\d+)", duration_str)
                    if duration_match:
                        duration_minutes = int(duration_match.group(1))
                elif text.startswith("Género:"):
                    genre = text.replace("Género:", "").strip()
                elif text.startswith("Estreno:"):
                    date_str = text.replace("Estreno:", "").strip()
                    release_date = CineproxScraperAndHTMLParser._parse_release_date(date_str)
                elif text.startswith("País:"):
                    country = text.replace("País:", "").strip()
                elif text.startswith("Director:"):
                    director = text.replace("Director:", "").strip()
                elif text.startswith("Reparto:"):
                    reparto_str = text.replace("Reparto:", "").strip()
                    actors = [a.strip() for a in reparto_str.split("-") if a.strip()]

        img_elem = pelicula_section.find("img", class_="card-img-top")
        if img_elem and img_elem.get("src"):
            poster_url = str(img_elem["src"])

        return CineproxMovieMetadata(
            title=title,
            original_title=original_title,
            synopsis=synopsis,
            classification=classification,
            duration_minutes=duration_minutes,
            genre=genre,
            release_date=release_date,
            country=country,
            director=director,
            actors=actors,
            poster_url=poster_url,
        )

    @staticmethod
    def _parse_release_date(date_str: str) -> datetime.date | None:
        """Parse date string like '22/enero/2026' or '22/01/2026'."""
        month_names = {
            "enero": 1, "febrero": 2, "marzo": 3, "abril": 4,
            "mayo": 5, "junio": 6, "julio": 7, "agosto": 8,
            "septiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
        }

        match = re.match(r"(\d{1,2})/(\w+)/(\d{4})", date_str)
        if match:
            day = int(match.group(1))
            month_str = match.group(2).lower()
            year = int(match.group(3))

            month = month_names.get(month_str)
            if month:
                try:
                    return datetime.date(year, month, day)
                except ValueError:
                    return None

        match_numeric = re.match(r"(\d{1,2})/(\d{1,2})/(\d{4})", date_str)
        if match_numeric:
            day = int(match_numeric.group(1))
            month = int(match_numeric.group(2))
            year = int(match_numeric.group(3))
            try:
                return datetime.date(year, month, day)
            except ValueError:
                return None

        return None

    @staticmethod
    def parse_showtimes_from_detail_html(
        html_content: str,
        selected_date: datetime.date,
        theater_name: str,
    ) -> list[CineproxShowtime]:
        soup = BeautifulSoup(html_content, "lxml")

        showtimes: list[CineproxShowtime] = []

        accordion_items = soup.find_all("div", class_="accordion-item")

        for accordion in accordion_items:
            header_button = accordion.find("button", class_="accordion-button")
            if not header_button:
                continue

            accordion_theater_name = header_button.get_text(strip=True)
            if not CineproxScraperAndHTMLParser._theater_names_match(
                accordion_theater_name, theater_name
            ):
                continue

            collapse_div = accordion.find("div", class_="accordion-collapse")
            if not collapse_div:
                continue

            tab_panes = collapse_div.find_all("div", id="pills-todas")
            if not tab_panes:
                tab_panes = collapse_div.find_all("div", class_="tab-pane")

            for tab_pane in tab_panes:
                room_type_elem = tab_pane.find("h5", class_="tipoSala")
                room_type = ""
                if room_type_elem:
                    b_elem = room_type_elem.find("b")
                    room_type = b_elem.get_text(strip=True) if b_elem else room_type_elem.get_text(strip=True)

                schedule_cards = tab_pane.find_all("div", class_="col-sm-6")
                if not schedule_cards:
                    schedule_cards = [div for div in tab_pane.find_all("div") if any("col-" in c for c in (div.get("class") or []))]

                for schedule_div in schedule_cards:
                    header = schedule_div.find("div", class_="movie-schedule-header")
                    card = schedule_div.find("div", class_="movie-schedule-card")

                    if not header or not card:
                        continue

                    format_text = header.get_text(strip=True)
                    format_str, translation_type = CineproxScraperAndHTMLParser._parse_format_and_language(format_text)

                    time_elem = card.find("div", class_="movie-schedule-time")
                    if not time_elem:
                        continue
                    time_text = time_elem.get_text(strip=True)
                    parsed_time = parse_time_string(time_text)
                    if not parsed_time:
                        logger.warning(f"Could not parse time: {time_text}")
                        OperationalIssue.objects.create(
                            name="Time Parse Failed",
                            task="cineprox_download_task",
                            error_message=f"Could not parse time string: '{time_text}'",
                            context={"theater": theater_name, "date": str(selected_date)},
                            severity=OperationalIssue.Severity.WARNING,
                        )
                        continue

                    price_elem = card.find("div", class_="movie-schedule-price")
                    price = price_elem.get_text(strip=True) if price_elem else None

                    showtimes.append(CineproxShowtime(
                        date=selected_date,
                        time=parsed_time,
                        format=format_str,
                        translation_type=translation_type,
                        room_type=room_type,
                        price=price,
                    ))

        return showtimes

    @staticmethod
    def _theater_names_match(accordion_name: str, target_name: str) -> bool:
        """Check if accordion theater name matches our target theater."""
        accordion_normalized = accordion_name.lower().strip()
        target_normalized = target_name.lower().strip()

        if target_normalized in accordion_normalized:
            return True

        target_parts = target_normalized.split()
        accordion_parts = accordion_normalized.split()

        matches = sum(1 for part in target_parts if part in accordion_parts)
        return matches >= len(target_parts) // 2 + 1

    @staticmethod
    def _parse_format_and_language(format_text: str) -> tuple[str, str]:
        """Parse format text like '2D - DOB' into format and translation_type."""
        translation_type_map = {
            "DOB": "Doblada",
            "SUB": "Subtitulada",
        }
        parts = format_text.split("-")
        format_str = parts[0].strip() if parts else ""
        language_code = parts[1].strip() if len(parts) > 1 else ""
        translation_type = translation_type_map.get(language_code, language_code)
        return format_str, translation_type

    @staticmethod
    def parse_available_dates_from_detail_html(html_content: str, reference_year: int) -> list[datetime.date]:
        soup = BeautifulSoup(html_content, "lxml")

        dates: list[datetime.date] = []
        today = datetime.datetime.now(BOGOTA_TZ).date()

        calendar_container = soup.find("div", class_="calendar-container")
        if not calendar_container:
            return dates

        day_items = calendar_container.find_all("div", class_="day-item")

        for day_item in day_items:
            date_span = day_item.find("span", class_="date")
            if not date_span:
                continue

            date_text = date_span.get_text(strip=True)
            parsed_date = CineproxScraperAndHTMLParser._parse_calendar_date(date_text, reference_year)

            if parsed_date:
                delta_days = (parsed_date - today).days
                if delta_days > 180:
                    parsed_date = parsed_date.replace(year=parsed_date.year - 1)
                elif delta_days < -180:
                    parsed_date = parsed_date.replace(year=parsed_date.year + 1)

                dates.append(parsed_date)

        return dates

    @staticmethod
    def _parse_calendar_date(date_text: str, reference_year: int) -> datetime.date | None:
        """Parse calendar date like '24 ene' or '25 ene'."""
        match = re.match(r"(\d{1,2})\s+(\w{3})", date_text.lower())
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
    def is_theater_accordion_expanded(html_content: str, theater_name: str) -> bool:
        """Check if the accordion for the given theater is expanded (has class 'show')."""
        soup = BeautifulSoup(html_content, "lxml")

        accordion_items = soup.find_all("div", class_="accordion-item")

        for accordion in accordion_items:
            header_button = accordion.find("button", class_="accordion-button")
            if not header_button:
                continue

            accordion_theater_name = header_button.get_text(strip=True)
            if not CineproxScraperAndHTMLParser._theater_names_match(
                accordion_theater_name, theater_name
            ):
                continue

            collapse_div = accordion.find("div", class_="accordion-collapse")
            if not collapse_div:
                continue

            class_attr = collapse_div.get("class")
            classes = list(class_attr) if class_attr else []
            return "show" in classes

        return False

    @staticmethod
    def generate_movie_detail_url(
        movie_id: str,
        slug: str,
        city_id: str | None,
        theater_id: str | None,
    ) -> str:
        base_url = f"https://www.cineprox.com/detalle-pelicula/{movie_id}-{slug}"
        if city_id and theater_id:
            params = urlencode({"idCiudad": city_id, "idTeatro": theater_id})
            return f"{base_url}?{params}"
        return base_url

    @staticmethod
    def generate_movie_source_url(movie_id: str, slug: str) -> str:
        return f"https://www.cineprox.com/detalle-pelicula/{movie_id}-{slug}"


class CineproxShowtimeSaver:
    """Coordinates scraping and saves movies/showtimes to the database."""

    def __init__(
        self,
        scraper: CineproxScraperAndHTMLParser,
        tmdb_service: TMDBService,
        storage_service: SupabaseStorageService | None,
    ):
        self.scraper = scraper
        self.lookup_service = MovieLookupService(tmdb_service, storage_service, SOURCE_NAME)
        self.processed_movies: dict[str, Movie | None] = {}
        self.tmdb_calls = 0
        self.new_movies: list[str] = []

    def execute(self) -> TaskReport:
        theaters = Theater.objects.filter(scraper_type="cineprox")
        total_showtimes = 0

        for theater in theaters:
            try:
                showtimes_for_theater = self._process_theater(theater)
                total_showtimes += showtimes_for_theater
            except Exception as e:
                logger.error(f"Failed to process theater {theater.name}: {e}")
                OperationalIssue.objects.create(
                    name="Cineprox Theater Processing Failed",
                    task="cineprox_download_task",
                    error_message=str(e),
                    traceback=traceback.format_exc(),
                    context={"theater_name": theater.name, "theater_slug": theater.slug},
                    severity=OperationalIssue.Severity.ERROR,
                )

        return TaskReport(
            total_showtimes=total_showtimes,
            tmdb_calls=self.tmdb_calls,
            new_movies=self.new_movies,
        )

    def execute_for_theater(self, theater: Theater) -> int:
        """Process a single theater and return the number of showtimes saved."""
        return self._process_theater(theater)

    def _process_theater(self, theater: Theater) -> int:
        logger.info(f"Processing Cineprox theater: {theater.name}\n\n")

        scraper_config = theater.scraper_config
        if not scraper_config:
            logger.error(f"No scraper_config for theater {theater.name}")
            OperationalIssue.objects.create(
                name="Cineprox Missing Scraper Config",
                task="cineprox_download_task",
                error_message=f"Theater {theater.name} has no scraper_config",
                context={"theater_slug": theater.slug},
                severity=OperationalIssue.Severity.ERROR,
            )
            return 0

        city_id = scraper_config.get("city_id")
        theater_id = scraper_config.get("theater_id")

        if not city_id or not theater_id:
            logger.error(f"Incomplete scraper_config for theater {theater.name}")
            OperationalIssue.objects.create(
                name="Cineprox Incomplete Scraper Config",
                task="cineprox_download_task",
                error_message=f"Theater {theater.name} missing city_id or theater_id",
                context={"theater_slug": theater.slug, "scraper_config": scraper_config},
                severity=OperationalIssue.Severity.ERROR,
            )
            return 0

        cartelera_url = theater.download_source_url
        if not cartelera_url:
            logger.error(f"No download_source_url for theater {theater.name}")
            return 0

        html_content = self.scraper.download_cartelera_html(cartelera_url)
        movie_cards = self.scraper.parse_movies_from_cartelera_html(html_content)

        if not movie_cards:
            logger.warning(f"No movies found in cartelera for {theater.name}")
            OperationalIssue.objects.create(
                name="Cineprox No Movies Found",
                task="cineprox_download_task",
                error_message=f"No movies found in cartelera for {theater.name}",
                context={"cartelera_url": cartelera_url},
                severity=OperationalIssue.Severity.WARNING,
            )
            return 0

        active_movies = [m for m in movie_cards if m.category != "pronto"]
        logger.info(f"Found {len(movie_cards)} movies, {len(active_movies)} active (excluding 'pronto')")

        all_showtimes: list[tuple[Movie, str, list[CineproxShowtime]]] = []

        for movie_card in active_movies:
            try:
                movie_showtimes = self._collect_showtimes_for_movie(
                    movie_card, theater, city_id, theater_id
                )
                if movie_showtimes:
                    all_showtimes.append(movie_showtimes)
            except Exception as e:
                logger.error(f"Failed to process movie {movie_card.title}: {e}")
                OperationalIssue.objects.create(
                    name="Cineprox Movie Processing Failed",
                    task="cineprox_download_task",
                    error_message=str(e),
                    traceback=traceback.format_exc(),
                    context={"movie_title": movie_card.title, "movie_id": movie_card.movie_id},
                    severity=OperationalIssue.Severity.WARNING,
                )

        total_showtimes = self._save_all_showtimes_for_theater(theater, all_showtimes)
        return total_showtimes

    def _collect_showtimes_for_movie(
        self,
        movie_card: CineproxMovieCard,
        theater: Theater,
        city_id: str,
        theater_id: str,
    ) -> tuple[Movie, str, list[CineproxShowtime]] | None:
        """Collect showtimes for a movie without saving to database."""
        detail_url = self.scraper.generate_movie_detail_url(
            movie_card.movie_id, movie_card.slug, city_id, theater_id
        )
        source_url = self.scraper.generate_movie_source_url(movie_card.movie_id, movie_card.slug)

        logger.info(f"Processing movie: {movie_card.title}")

        html_content = self.scraper.download_movie_detail_html(detail_url)

        if not self.scraper.is_theater_accordion_expanded(html_content, theater.name):
            logger.warning(f"Theater accordion not expanded for {theater.name}")
            OperationalIssue.objects.create(
                name="Cineprox Theater Accordion Not Expanded",
                task="cineprox_download_task",
                error_message=f"Theater accordion not expanded for {theater.name}. Check if theater_id is correct.",
                context={
                    "theater_name": theater.name,
                    "theater_id": theater_id,
                    "movie_url": detail_url,
                },
                severity=OperationalIssue.Severity.WARNING,
            )

        result = self._get_or_create_movie(movie_card, source_url, html_content)
        movie = result.movie

        if result.tmdb_called:
            self.tmdb_calls += 1
        if result.is_new and movie:
            self.new_movies.append(movie.title_es)

        if not movie:
            logger.debug(f"Skipping showtimes for unfindable movie: {movie_card.title}")
            return None

        today = datetime.datetime.now(BOGOTA_TZ).date()
        reference_year = today.year
        available_dates = self.scraper.parse_available_dates_from_detail_html(
            html_content, reference_year
        )

        if not available_dates:
            available_dates = [today]

        all_showtimes: list[CineproxShowtime] = []

        for date in available_dates:
            showtimes = self.scraper.parse_showtimes_from_detail_html(
                html_content, date, theater.name
            )
            all_showtimes.extend(showtimes)

        if not all_showtimes:
            return None

        return (movie, detail_url, all_showtimes)

    def _get_or_create_movie(
        self,
        movie_card: CineproxMovieCard,
        source_url: str,
        html_content: str,
    ) -> MovieLookupResult:
        cache_key = source_url
        if cache_key in self.processed_movies:
            movie = self.processed_movies[cache_key]
            return MovieLookupResult(movie=movie, is_new=False, tmdb_called=False)

        existing_movie = MovieSourceUrl.get_movie_for_source_url(
            url=source_url,
            scraper_type=MovieSourceUrl.ScraperType.CINEPROX,
        )
        if existing_movie:
            self.processed_movies[cache_key] = existing_movie
            return MovieLookupResult(movie=existing_movie, is_new=False, tmdb_called=False)

        metadata = self._extract_metadata(movie_card.title, html_content)

        result = self.lookup_service.get_or_create_movie(
            movie_name=movie_card.title,
            source_url=source_url,
            scraper_type=MovieSourceUrl.ScraperType.CINEPROX,
            metadata=metadata,
        )

        self.processed_movies[cache_key] = result.movie
        return result

    def _extract_metadata(self, movie_title: str, html_content: str) -> MovieMetadata | None:
        cineprox_meta = self.scraper.parse_movie_metadata_from_detail_html(html_content)
        if not cineprox_meta:
            logger.warning(f"Could not extract metadata for '{movie_title}'")
            return None

        release_year: int | None = None
        if cineprox_meta.release_date:
            release_year = cineprox_meta.release_date.year

        return MovieMetadata(
            genre=cineprox_meta.genre,
            duration_minutes=cineprox_meta.duration_minutes,
            classification=cineprox_meta.classification,
            director=cineprox_meta.director,
            actors=cineprox_meta.actors,
            original_title=cineprox_meta.original_title,
            release_date=cineprox_meta.release_date,
            release_year=release_year,
            trailer_url=None,
        )

    @transaction.atomic
    def _save_all_showtimes_for_theater(
        self,
        theater: Theater,
        movie_showtimes: list[tuple[Movie, str, list[CineproxShowtime]]],
    ) -> int:
        """Delete all existing showtimes for theater and save new ones atomically."""
        deleted_count, _ = Showtime.objects.filter(
            theater=theater,
        ).delete()
        if deleted_count:
            logger.info(f"Deleted {deleted_count} existing Cineprox showtimes for {theater.name}")

        showtimes_saved = 0

        for movie, source_url, showtimes in movie_showtimes:
            for showtime in showtimes:
                translation_type = normalize_translation_type(
                    showtime.translation_type,
                    task="cineprox_download_task",
                    context={"theater": theater.name, "movie": movie.title_es},
                )
                Showtime.objects.create(
                    theater=theater,
                    movie=movie,
                    start_date=showtime.date,
                    start_time=showtime.time,
                    format=showtime.format,
                    translation_type=translation_type,
                    screen=showtime.room_type,
                    source_url=source_url,
                )
                showtimes_saved += 1

        logger.info(f"Saved {showtimes_saved} showtimes for {theater.name}")
        return showtimes_saved


@app.task
def cineprox_download_task():
    logger.info("Starting cineprox_download_task")

    try:
        scraper = CineproxScraperAndHTMLParser()
        tmdb_service = TMDBService()
        storage_service = SupabaseStorageService.create_from_settings()
        if not storage_service:
            raise RuntimeError("Failed to create storage service")

        saver = CineproxShowtimeSaver(scraper, tmdb_service, storage_service)
        report = saver.execute()
        report.print_report()
        return report

    except Exception as e:
        logger.error(f"Failed Cineprox download task: {e}")
        OperationalIssue.objects.create(
            name="Cineprox Download Task Failed",
            task="cineprox_download_task",
            error_message=str(e),
            traceback=traceback.format_exc(),
            context={},
            severity=OperationalIssue.Severity.ERROR,
        )
        raise
