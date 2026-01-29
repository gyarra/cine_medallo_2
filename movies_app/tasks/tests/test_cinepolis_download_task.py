"""Tests for Cinepolis download task."""

import datetime
from pathlib import Path

import pytest

from movies_app.tasks.cinepolis_download_task import CinepolisScraperAndHTMLParser


@pytest.fixture
def home_page_html() -> str:
    html_path = Path(__file__).parent / "html_snapshot" / "cinepolis___all_movies.html"
    return html_path.read_text()


@pytest.fixture
def theater_page_html() -> str:
    html_path = Path(__file__).parent / "html_snapshot" / "cinepolis___movies_for_one_theater.html"
    return html_path.read_text()


class TestParseMoviesFromHomePage:
    """Tests for parsing movies from the home page."""

    def test_parse_movies_returns_list(self, home_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        movies = parser.parse_movies_from_home_page_html(home_page_html)
        assert isinstance(movies, list)
        assert len(movies) > 0

    def test_parse_movies_extracts_titles(self, home_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        movies = parser.parse_movies_from_home_page_html(home_page_html)
        titles = [m.title for m in movies]
        assert "Sin Piedad" in titles
        assert "Anaconda" in titles
        assert "La empleada" in titles

    def test_parse_movies_extracts_slugs(self, home_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        movies = parser.parse_movies_from_home_page_html(home_page_html)
        slugs = [m.slug for m in movies]
        assert "sin-piedad" in slugs
        assert "anaconda" in slugs

    def test_parse_movies_constructs_urls(self, home_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        movies = parser.parse_movies_from_home_page_html(home_page_html)
        anaconda = next((m for m in movies if m.slug == "anaconda"), None)
        assert anaconda is not None
        assert anaconda.url == "https://cinepolis.com.co/pelicula/anaconda"

    def test_parse_movies_extracts_poster_urls(self, home_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        movies = parser.parse_movies_from_home_page_html(home_page_html)
        for movie in movies:
            if movie.poster_url:
                assert "cinepolis.com" in movie.poster_url

    def test_parse_movies_no_duplicates(self, home_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        movies = parser.parse_movies_from_home_page_html(home_page_html)
        slugs = [m.slug for m in movies]
        assert len(slugs) == len(set(slugs))


class TestParseShowtimesFromTheaterPage:
    """Tests for parsing showtimes from theater page."""

    def test_parse_showtimes_returns_list(self, theater_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        showtimes = parser.parse_showtimes_from_theater_html(
            theater_page_html,
            "27 enero"
        )
        assert isinstance(showtimes, list)
        assert len(showtimes) > 0

    def test_parse_showtimes_extracts_movie_titles(self, theater_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        showtimes = parser.parse_showtimes_from_theater_html(
            theater_page_html,
            "27 enero"
        )
        titles = {title for title, _ in showtimes}
        assert "Avatar: Fuego y Cenizas" in titles
        assert "Zootopia 2" in titles
        assert "Sin Piedad" in titles

    def test_parse_showtimes_extracts_times(self, theater_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        showtimes = parser.parse_showtimes_from_theater_html(
            theater_page_html,
            "27 enero"
        )
        avatar_showtimes = [st for title, st in showtimes if title == "Avatar: Fuego y Cenizas"]
        times = [st.time for st in avatar_showtimes]
        assert datetime.time(17, 0) in times
        assert datetime.time(20, 0) in times
        assert datetime.time(21, 0) in times

    def test_parse_showtimes_extracts_format(self, theater_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        showtimes = parser.parse_showtimes_from_theater_html(
            theater_page_html,
            "27 enero"
        )
        # La empleada has DIG SUB format
        empleada_showtimes = [st for title, st in showtimes if title == "La empleada"]
        formats = {st.format for st in empleada_showtimes}
        assert "DIG" in formats or any("DIG" in f for f in formats if f)

    def test_parse_showtimes_extracts_translation_type(self, theater_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        showtimes = parser.parse_showtimes_from_theater_html(
            theater_page_html,
            "27 enero"
        )
        # Most movies have DOB (dubbed) showtimes
        translation_types = {st.translation_type for _, st in showtimes}
        assert "DOB" in translation_types
        # Sin Piedad has SUB showtimes
        assert "SUB" in translation_types

    def test_parse_showtimes_sets_correct_date(self, theater_page_html: str) -> None:
        parser = CinepolisScraperAndHTMLParser()
        # Use a date that will parse correctly
        showtimes = parser.parse_showtimes_from_theater_html(
            theater_page_html,
            "27 enero"
        )
        for _, st in showtimes:
            assert st.date.month == 1
            assert st.date.day == 27


class TestParseDateFromText:
    """Tests for date parsing."""

    def test_parse_simple_date(self) -> None:
        parser = CinepolisScraperAndHTMLParser()
        date = parser.parse_date_from_text("27 enero")
        assert date is not None
        assert date.day == 27
        assert date.month == 1

    def test_parse_today_format(self) -> None:
        parser = CinepolisScraperAndHTMLParser()
        date = parser.parse_date_from_text("Hoy (27 enero)")
        assert date is not None
        assert date.day == 27
        assert date.month == 1

    def test_parse_tomorrow_format(self) -> None:
        parser = CinepolisScraperAndHTMLParser()
        date = parser.parse_date_from_text("Mañana (28 enero)")
        assert date is not None
        assert date.day == 28
        assert date.month == 1

    def test_parse_february_date(self) -> None:
        parser = CinepolisScraperAndHTMLParser()
        date = parser.parse_date_from_text("05 febrero")
        assert date is not None
        assert date.day == 5
        assert date.month == 2

    def test_parse_invalid_date_returns_none(self) -> None:
        parser = CinepolisScraperAndHTMLParser()
        date = parser.parse_date_from_text("invalid")
        assert date is None


class TestParseTime:
    """Tests for time parsing."""

    def test_parse_24_hour_time(self) -> None:
        parser = CinepolisScraperAndHTMLParser()
        time = parser._parse_time("17:00")
        assert time is not None
        assert time.hour == 17
        assert time.minute == 0

    def test_parse_early_time(self) -> None:
        parser = CinepolisScraperAndHTMLParser()
        time = parser._parse_time("14:40")
        assert time is not None
        assert time.hour == 14
        assert time.minute == 40

    def test_parse_late_time(self) -> None:
        parser = CinepolisScraperAndHTMLParser()
        time = parser._parse_time("22:00")
        assert time is not None
        assert time.hour == 22
        assert time.minute == 0

    def test_parse_invalid_time_returns_none(self) -> None:
        parser = CinepolisScraperAndHTMLParser()
        time = parser._parse_time("invalid")
        assert time is None
