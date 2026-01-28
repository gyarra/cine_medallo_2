import datetime
import os

import pytest

from movies_app.tasks.royal_download_task import (
    RoyalScraperAndHTMLParser,
)


class TestParseMoviesFromTheaterHtml:
    """Tests for parsing movies from the theater's cartelera page."""

    @pytest.fixture
    def theater_html(self) -> str:
        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "royal___movies_for_one_theater.html",
        )
        with open(html_snapshot_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_extracts_movie_titles(self, theater_html: str):
        movies = RoyalScraperAndHTMLParser.parse_movies_from_theater_html(theater_html)
        titles = [m.title for m in movies]

        expected_titles = [
            "Sin Piedad",
            "Marty Supremo",
            "El Descenso",
            "Moon: Mi Amigo El Panda",
            "Goat: La Cabra Que Cambió El Juego",
            "Avatar: Fuego Y Cenizas",
            "Exterminio: El Templo De Huesos",
            "Zootopia 2",
        ]

        assert len(movies) == 8
        assert titles == expected_titles

    def test_extracts_movie_urls(self, theater_html: str):
        movies = RoyalScraperAndHTMLParser.parse_movies_from_theater_html(theater_html)

        for movie in movies:
            assert movie.url.startswith("https://cinemasroyalfilms.com/pelicula/")
            assert movie.movie_id.isdigit()
            assert len(movie.slug) > 0

    def test_extracts_movie_ids_correctly(self, theater_html: str):
        movies = RoyalScraperAndHTMLParser.parse_movies_from_theater_html(theater_html)
        movie_ids = [m.movie_id for m in movies]

        assert "3889" in movie_ids
        assert "3873" in movie_ids
        assert "3728" in movie_ids

    def test_extracts_poster_urls(self, theater_html: str):
        movies = RoyalScraperAndHTMLParser.parse_movies_from_theater_html(theater_html)

        for movie in movies:
            if movie.poster_url:
                assert "admin.cinemasroyalfilms.com" in movie.poster_url

    def test_does_not_include_duplicates(self, theater_html: str):
        movies = RoyalScraperAndHTMLParser.parse_movies_from_theater_html(theater_html)
        urls = [m.url for m in movies]

        assert len(urls) == len(set(urls))


class TestParseShowtimesFromMovieHtml:
    """Tests for parsing showtimes from the individual movie page."""

    @pytest.fixture
    def movie_html(self) -> str:
        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "royal___one_movie.html",
        )
        with open(html_snapshot_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_extracts_showtimes_for_matching_theater(self, movie_html: str):
        selected_date = datetime.date(2025, 1, 27)
        showtimes = RoyalScraperAndHTMLParser.parse_showtimes_from_movie_html(
            movie_html, "Multicine Jumbo La 65", selected_date
        )

        assert len(showtimes) == 3

        times = [st.time for st in showtimes]
        assert datetime.time(16, 30) in times
        assert datetime.time(19, 0) in times
        assert datetime.time(21, 30) in times

    def test_extracts_format_and_translation_type(self, movie_html: str):
        selected_date = datetime.date(2025, 1, 27)
        showtimes = RoyalScraperAndHTMLParser.parse_showtimes_from_movie_html(
            movie_html, "Multicine Jumbo La 65", selected_date
        )

        for st in showtimes:
            assert st.format == "2D"
            # Parser returns raw value; normalization happens in the saver
            assert st.translation_type == "DOB"

    def test_returns_empty_for_nonexistent_theater(self, movie_html: str):
        selected_date = datetime.date(2025, 1, 27)
        showtimes = RoyalScraperAndHTMLParser.parse_showtimes_from_movie_html(
            movie_html, "Nonexistent Theater", selected_date
        )

        assert len(showtimes) == 0

    def test_extracts_showtimes_for_different_theaters(self, movie_html: str):
        selected_date = datetime.date(2025, 1, 27)

        jumbo_showtimes = RoyalScraperAndHTMLParser.parse_showtimes_from_movie_html(
            movie_html, "Multicine Jumbo La 65", selected_date
        )
        assert len(jumbo_showtimes) == 3

        premium_showtimes = RoyalScraperAndHTMLParser.parse_showtimes_from_movie_html(
            movie_html, "Multicine Premium Plaza", selected_date
        )
        assert len(premium_showtimes) == 1
        assert premium_showtimes[0].time == datetime.time(17, 20)

        bosque_showtimes = RoyalScraperAndHTMLParser.parse_showtimes_from_movie_html(
            movie_html, "Multicine Bosque Plaza", selected_date
        )
        assert len(bosque_showtimes) == 1
        assert bosque_showtimes[0].time == datetime.time(19, 10)


class TestParseAvailableDates:
    """Tests for parsing available dates from the movie page calendar."""

    @pytest.fixture
    def movie_html(self) -> str:
        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "royal___one_movie.html",
        )
        with open(html_snapshot_path, "r", encoding="utf-8") as f:
            return f.read()

    def test_extracts_dates_from_calendar(self, movie_html: str):
        dates = RoyalScraperAndHTMLParser.parse_available_dates_from_movie_html(movie_html)

        assert len(dates) == 2
        # Check month/day regardless of year (year adjustment depends on current date)
        date_tuples = [(d.month, d.day) for d in dates]
        assert (1, 27) in date_tuples
        assert (1, 28) in date_tuples


class TestParseDateTabText:
    """Tests for parsing date tab text."""

    def test_parses_standard_format(self):
        result = RoyalScraperAndHTMLParser._parse_date_tab_text("mar 27 ene", 2025)
        assert result == datetime.date(2025, 1, 27)

    def test_parses_with_different_days(self):
        assert RoyalScraperAndHTMLParser._parse_date_tab_text("mié 28 ene", 2025) == datetime.date(2025, 1, 28)
        assert RoyalScraperAndHTMLParser._parse_date_tab_text("jue 1 feb", 2025) == datetime.date(2025, 2, 1)
        assert RoyalScraperAndHTMLParser._parse_date_tab_text("vie 15 dic", 2025) == datetime.date(2025, 12, 15)

    def test_returns_none_for_invalid_format(self):
        assert RoyalScraperAndHTMLParser._parse_date_tab_text("invalid", 2025) is None
        assert RoyalScraperAndHTMLParser._parse_date_tab_text("", 2025) is None


class TestParseFormatAndTranslation:
    """Tests for parsing format and translation type.

    Parser returns raw values - normalization happens in the saver.
    """

    def test_parses_2d_dob(self):
        format_str, translation = RoyalScraperAndHTMLParser._parse_format_and_translation("2D - DOB")
        assert format_str == "2D"
        assert translation == "DOB"

    def test_parses_3d_sub(self):
        format_str, translation = RoyalScraperAndHTMLParser._parse_format_and_translation("3D - SUB")
        assert format_str == "3D"
        assert translation == "SUB"

    def test_parses_format_only(self):
        format_str, translation = RoyalScraperAndHTMLParser._parse_format_and_translation("2D")
        assert format_str == "2D"
        assert translation == ""

    def test_parses_imax(self):
        format_str, translation = RoyalScraperAndHTMLParser._parse_format_and_translation("IMAX - DOB")
        assert format_str == "IMAX"
        assert translation == "DOB"


class TestParseRoyalTime:
    """Tests for parsing Royal Films time strings."""

    def test_parses_pm_time(self):
        assert RoyalScraperAndHTMLParser._parse_royal_time("04:30 p. m.") == datetime.time(16, 30)
        assert RoyalScraperAndHTMLParser._parse_royal_time("07:00 p. m.") == datetime.time(19, 0)
        assert RoyalScraperAndHTMLParser._parse_royal_time("09:30 p. m.") == datetime.time(21, 30)

    def test_parses_am_time(self):
        assert RoyalScraperAndHTMLParser._parse_royal_time("10:30 a. m.") == datetime.time(10, 30)
        assert RoyalScraperAndHTMLParser._parse_royal_time("11:00 a. m.") == datetime.time(11, 0)

    def test_parses_noon(self):
        assert RoyalScraperAndHTMLParser._parse_royal_time("12:00 p. m.") == datetime.time(12, 0)
        assert RoyalScraperAndHTMLParser._parse_royal_time("12:30 p. m.") == datetime.time(12, 30)

    def test_parses_midnight(self):
        assert RoyalScraperAndHTMLParser._parse_royal_time("12:00 a. m.") == datetime.time(0, 0)

    def test_parses_compact_format(self):
        assert RoyalScraperAndHTMLParser._parse_royal_time("04:30p.m.") == datetime.time(16, 30)
        assert RoyalScraperAndHTMLParser._parse_royal_time("07:00pm") == datetime.time(19, 0)

    def test_returns_none_for_invalid(self):
        assert RoyalScraperAndHTMLParser._parse_royal_time("invalid") is None
        assert RoyalScraperAndHTMLParser._parse_royal_time("") is None


class TestTheaterNamesMatch:
    """Tests for theater name matching logic."""

    def test_exact_match(self):
        assert RoyalScraperAndHTMLParser._theater_names_match("Multicine Jumbo La 65", "Multicine Jumbo La 65")

    def test_case_insensitive(self):
        assert RoyalScraperAndHTMLParser._theater_names_match("MULTICINE JUMBO LA 65", "multicine jumbo la 65")

    def test_partial_match_with_prefix(self):
        assert RoyalScraperAndHTMLParser._theater_names_match("Royal Films - Multicine Jumbo La 65", "Multicine Jumbo La 65")

    def test_word_overlap_match(self):
        assert RoyalScraperAndHTMLParser._theater_names_match("Jumbo La 65", "Multicine Jumbo La 65")

    def test_no_match_for_different_theaters(self):
        assert not RoyalScraperAndHTMLParser._theater_names_match("Multicine Premium Plaza", "Multicine Jumbo La 65")


class TestHasNoShowtimesMessage:
    """Tests for detecting 'no showtimes' message."""

    def test_returns_true_when_message_present(self):
        html = '<div class="alert">No se encontró ninguna función</div>'
        assert RoyalScraperAndHTMLParser.has_no_showtimes_message(html) is True

    def test_returns_false_when_message_absent(self):
        html = '<div id="accordionFunctions"><div class="showtime">4:30 PM</div></div>'
        assert RoyalScraperAndHTMLParser.has_no_showtimes_message(html) is False


class TestExtractMovieIdAndSlug:
    """Tests for extracting movie ID and slug from href."""

    def test_extracts_from_standard_href(self):
        movie_id, slug = RoyalScraperAndHTMLParser._extract_movie_id_and_slug("/pelicula/3889/sin-piedad")
        assert movie_id == "3889"
        assert slug == "sin-piedad"

    def test_extracts_from_href_with_special_chars(self):
        movie_id, slug = RoyalScraperAndHTMLParser._extract_movie_id_and_slug("/pelicula/3890/moon:-mi-amigo-el-panda")
        assert movie_id == "3890"
        assert slug == "moon:-mi-amigo-el-panda"

    def test_returns_empty_for_invalid_href(self):
        movie_id, slug = RoyalScraperAndHTMLParser._extract_movie_id_and_slug("/invalid/path")
        assert movie_id == ""
        assert slug == ""
