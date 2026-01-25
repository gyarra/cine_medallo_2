import datetime
import os

from movies_app.tasks.cineprox_download_task import (
    CineproxScraperAndHTMLParser,
)


def load_html_snapshot(filename: str) -> str:
    html_snapshot_path = os.path.join(
        os.path.dirname(__file__),
        "html_snapshot",
        filename,
    )
    with open(html_snapshot_path, encoding="utf-8") as f:
        return f.read()


class TestParseMoviesFromCarteleraHtml:
    def test_extracts_movies_from_cartelera_html(self):
        html_content = load_html_snapshot("cineprox_cartelera_for_one_theater.html")

        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)

        assert len(movies) > 0

        movie_ids = {m.movie_id for m in movies}
        assert "2003" in movie_ids
        assert "2005" in movie_ids
        assert "1940" in movie_ids
        assert "1892" in movie_ids

    def test_extracts_correct_movie_data(self):
        html_content = load_html_snapshot("cineprox_cartelera_for_one_theater.html")

        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)

        sin_piedad_movies = [m for m in movies if m.movie_id == "2005"]
        assert len(sin_piedad_movies) == 1

        sin_piedad = sin_piedad_movies[0]
        assert sin_piedad.title == "SIN PIEDAD"
        assert sin_piedad.category == "estrenos"
        assert sin_piedad.slug == "sin-piedad"
        assert "pantallascineprox.com/img/peliculas/2005.jpg" in sin_piedad.poster_url

    def test_extracts_movie_categories(self):
        html_content = load_html_snapshot("cineprox_cartelera_for_one_theater.html")

        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)

        categories = {m.category for m in movies}
        assert "preventa" in categories
        assert "estrenos" in categories
        assert "cartelera" in categories
        assert "pronto" in categories

    def test_filters_pronto_movies_correctly(self):
        html_content = load_html_snapshot("cineprox_cartelera_for_one_theater.html")

        movies = CineproxScraperAndHTMLParser.parse_movies_from_cartelera_html(html_content)

        pronto_movies = [m for m in movies if m.category == "pronto"]
        active_movies = [m for m in movies if m.category != "pronto"]

        assert len(pronto_movies) > 0
        assert len(active_movies) > 0


class TestParseMovieMetadataFromDetailHtml:
    def test_extracts_metadata_from_detail_page(self):
        html_content = load_html_snapshot("cineprox_one_movie_for_one_theater.html")

        metadata = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html(html_content)

        assert metadata is not None
        assert metadata.title == "SIN PIEDAD"
        assert metadata.original_title == "MERCY"
        assert "detective Chris Raven" in metadata.synopsis
        assert metadata.classification == "12 Años"
        assert metadata.duration_minutes == 100
        assert metadata.genre == "Acción"
        assert metadata.country == "ESTADOS UNIDOS"
        assert metadata.director == "Timur Bekmambetov"
        assert "Chris Pratt" in metadata.actors
        assert "Rebecca Ferguson" in metadata.actors

    def test_extracts_release_date(self):
        html_content = load_html_snapshot("cineprox_one_movie_for_one_theater.html")

        metadata = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html(html_content)

        assert metadata is not None
        assert metadata.release_date is not None
        assert metadata.release_date.year == 2026
        assert metadata.release_date.month == 1
        assert metadata.release_date.day == 22

    def test_extracts_poster_url(self):
        html_content = load_html_snapshot("cineprox_one_movie_for_one_theater.html")

        metadata = CineproxScraperAndHTMLParser.parse_movie_metadata_from_detail_html(html_content)

        assert metadata is not None
        assert "pantallascineprox.com/img/peliculas/2005.jpg" in metadata.poster_url


class TestParseShowtimesFromDetailHtml:
    def test_extracts_showtimes_for_theater(self):
        html_content = load_html_snapshot("cineprox_one_movie_for_one_theater.html")

        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Parque Fabricato",
        )

        assert len(showtimes) > 0

    def test_extracts_correct_showtime_data(self):
        html_content = load_html_snapshot("cineprox_one_movie_for_one_theater.html")

        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Parque Fabricato",
        )

        assert len(showtimes) >= 3

        times = {st.time for st in showtimes}
        assert datetime.time(16, 25) in times
        assert datetime.time(18, 40) in times
        assert datetime.time(21, 25) in times

    def test_extracts_format_and_language(self):
        html_content = load_html_snapshot("cineprox_one_movie_for_one_theater.html")

        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Parque Fabricato",
        )

        assert len(showtimes) > 0
        first_showtime = showtimes[0]
        assert first_showtime.format == "2D"
        assert first_showtime.language == "Doblado"

    def test_extracts_room_type(self):
        html_content = load_html_snapshot("cineprox_one_movie_for_one_theater.html")

        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Parque Fabricato",
        )

        assert len(showtimes) > 0
        first_showtime = showtimes[0]
        assert first_showtime.room_type == "General"

    def test_extracts_price(self):
        html_content = load_html_snapshot("cineprox_one_movie_for_one_theater.html")

        showtimes = CineproxScraperAndHTMLParser.parse_showtimes_from_detail_html(
            html_content,
            datetime.date(2026, 1, 24),
            "Parque Fabricato",
        )

        assert len(showtimes) > 0
        first_showtime = showtimes[0]
        assert first_showtime.price is not None
        assert "21.900" in first_showtime.price


class TestParseAvailableDatesFromDetailHtml:
    def test_extracts_available_dates(self):
        html_content = load_html_snapshot("cineprox_one_movie_for_one_theater.html")

        dates = CineproxScraperAndHTMLParser.parse_available_dates_from_detail_html(
            html_content,
            reference_year=2026,
        )

        assert len(dates) >= 5

        days = {d.day for d in dates}
        assert 24 in days
        assert 25 in days
        assert 26 in days
        assert 27 in days
        assert 28 in days


class TestIsTheaterAccordionExpanded:
    def test_detects_expanded_accordion(self):
        html_content = load_html_snapshot("cineprox_one_movie_for_one_theater.html")

        is_expanded = CineproxScraperAndHTMLParser.is_theater_accordion_expanded(
            html_content,
            "Parque Fabricato",
        )

        assert is_expanded is True

    def test_detects_collapsed_accordion(self):
        html_content = load_html_snapshot("cineprox_one_movie_for_one_theater.html")

        is_expanded = CineproxScraperAndHTMLParser.is_theater_accordion_expanded(
            html_content,
            "Puerta del Norte",
        )

        assert is_expanded is False


class TestTheaterNamesMatch:
    def test_matches_exact_name(self):
        assert CineproxScraperAndHTMLParser._theater_names_match(
            "Parque Fabricato - Bello",
            "Parque Fabricato",
        ) is True

    def test_matches_partial_name(self):
        assert CineproxScraperAndHTMLParser._theater_names_match(
            "Puerta del Norte - Bello",
            "Puerta del Norte",
        ) is True

    def test_no_match_different_theaters(self):
        assert CineproxScraperAndHTMLParser._theater_names_match(
            "Parque Fabricato - Bello",
            "Puerta del Norte",
        ) is False


class TestParseFormatAndLanguage:
    def test_parses_2d_dob(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("2D - DOB")
        assert format_str == "2D"
        assert language == "Doblado"

    def test_parses_3d_sub(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("3D - SUB")
        assert format_str == "3D"
        assert language == "Subtitulado"

    def test_parses_2d_sub(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("2D - SUB")
        assert format_str == "2D"
        assert language == "Subtitulado"

    def test_parses_3d_dob(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("3D - DOB")
        assert format_str == "3D"
        assert language == "Doblado"

    def test_parses_format_only(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("2D")
        assert format_str == "2D"
        assert language == ""

    def test_unknown_language_code_preserved(self):
        format_str, language = CineproxScraperAndHTMLParser._parse_format_and_language("2D - ESP")
        assert format_str == "2D"
        assert language == "ESP"


class TestParseReleaseDate:
    def test_parses_spanish_month_format(self):
        date = CineproxScraperAndHTMLParser._parse_release_date("22/enero/2026")
        assert date is not None
        assert date.year == 2026
        assert date.month == 1
        assert date.day == 22

    def test_parses_numeric_format(self):
        date = CineproxScraperAndHTMLParser._parse_release_date("15/03/2026")
        assert date is not None
        assert date.year == 2026
        assert date.month == 3
        assert date.day == 15

    def test_returns_none_for_invalid_format(self):
        date = CineproxScraperAndHTMLParser._parse_release_date("invalid date")
        assert date is None


class TestGenerateUrls:
    def test_generate_movie_detail_url_with_params(self):
        url = CineproxScraperAndHTMLParser.generate_movie_detail_url(
            movie_id="2005",
            slug="sin-piedad",
            city_id="30",
            theater_id="328",
        )

        assert url == "https://www.cineprox.com/detalle-pelicula/2005-sin-piedad?idCiudad=30&idTeatro=328"

    def test_generate_movie_detail_url_without_params(self):
        url = CineproxScraperAndHTMLParser.generate_movie_detail_url(
            movie_id="2005",
            slug="sin-piedad",
            city_id=None,
            theater_id=None,
        )

        assert url == "https://www.cineprox.com/detalle-pelicula/2005-sin-piedad"

    def test_generate_movie_source_url(self):
        url = CineproxScraperAndHTMLParser.generate_movie_source_url(
            movie_id="2005",
            slug="sin-piedad",
        )

        assert url == "https://www.cineprox.com/detalle-pelicula/2005-sin-piedad"
