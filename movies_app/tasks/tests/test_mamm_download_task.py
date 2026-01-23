import datetime
import os

import pytest


class TestExtractShowtimesFromHtml:
    def test_extracts_showtimes_from_mamm_schedule_html(self):
        from movies_app.tasks.mamm_download_task import _extract_showtimes_from_html

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "elmamm_org_semana",
        )

        with open(html_snapshot_path, encoding="utf-8") as f:
            html_content = f.read()

        showtimes = _extract_showtimes_from_html(html_content)

        assert len(showtimes) > 0

        movie_titles = {st.movie_title for st in showtimes}
        assert "Perfect Blue" in movie_titles
        assert "La única opción" in movie_titles
        assert "Resurrección" in movie_titles

    def test_extracts_correct_showtime_data(self):
        from movies_app.tasks.mamm_download_task import _extract_showtimes_from_html

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "elmamm_org_semana",
        )

        with open(html_snapshot_path, encoding="utf-8") as f:
            html_content = f.read()

        showtimes = _extract_showtimes_from_html(html_content)

        perfect_blue_showtimes = [st for st in showtimes if st.movie_title == "Perfect Blue"]
        assert len(perfect_blue_showtimes) > 0

        first_perfect_blue = perfect_blue_showtimes[0]
        assert first_perfect_blue.time is not None
        assert first_perfect_blue.date is not None

    def test_extracts_movie_urls(self):
        from movies_app.tasks.mamm_download_task import _extract_showtimes_from_html

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "elmamm_org_semana",
        )

        with open(html_snapshot_path, encoding="utf-8") as f:
            html_content = f.read()

        showtimes = _extract_showtimes_from_html(html_content)

        showtimes_with_urls = [st for st in showtimes if st.movie_url is not None]
        assert len(showtimes_with_urls) > 0

        for st in showtimes_with_urls:
            assert st.movie_url is not None
            assert st.movie_url.startswith("https://www.elmamm.org/producto/")

    def test_extracts_special_labels(self):
        from movies_app.tasks.mamm_download_task import _extract_showtimes_from_html

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "elmamm_org_semana",
        )

        with open(html_snapshot_path, encoding="utf-8") as f:
            html_content = f.read()

        showtimes = _extract_showtimes_from_html(html_content)

        labeled_showtimes = [st for st in showtimes if st.special_label]
        assert len(labeled_showtimes) > 0

        labels = {st.special_label for st in labeled_showtimes}
        assert "Remasterizada en 4K" in labels or "Exclusivo Cine MAMM" in labels


class TestParseTimeString:
    def test_parses_pm_times(self):
        from movies_app.tasks.mamm_download_task import _parse_time_string

        assert _parse_time_string("2:00 pm") == datetime.time(14, 0)
        assert _parse_time_string("9:30 pm") == datetime.time(21, 30)
        assert _parse_time_string("12:00 pm") == datetime.time(12, 0)

    def test_parses_am_times(self):
        from movies_app.tasks.mamm_download_task import _parse_time_string

        assert _parse_time_string("10:00 am") == datetime.time(10, 0)
        assert _parse_time_string("12:00 am") == datetime.time(0, 0)

    def test_parses_times_with_periods(self):
        from movies_app.tasks.mamm_download_task import _parse_time_string

        assert _parse_time_string("2:00 p.m.") == datetime.time(14, 0)
        assert _parse_time_string("10:30 a.m.") == datetime.time(10, 30)

    def test_returns_none_for_invalid_time(self):
        from movies_app.tasks.mamm_download_task import _parse_time_string

        assert _parse_time_string("invalid") is None
        assert _parse_time_string("") is None


class TestParseDateString:
    def test_parses_spanish_dates(self):
        from movies_app.tasks.mamm_download_task import _parse_date_string

        assert _parse_date_string("viernes 23 Ene", 2025) == datetime.date(2025, 1, 23)
        assert _parse_date_string("sábado 24 Ene", 2025) == datetime.date(2025, 1, 24)
        assert _parse_date_string("domingo 25 Ene", 2025) == datetime.date(2025, 1, 25)

    def test_parses_different_months(self):
        from movies_app.tasks.mamm_download_task import _parse_date_string

        assert _parse_date_string("15 Feb", 2025) == datetime.date(2025, 2, 15)
        assert _parse_date_string("1 Dic", 2025) == datetime.date(2025, 12, 1)
        assert _parse_date_string("31 Jul", 2025) == datetime.date(2025, 7, 31)

    def test_returns_none_for_invalid_date(self):
        from movies_app.tasks.mamm_download_task import _parse_date_string

        assert _parse_date_string("invalid", 2025) is None
        assert _parse_date_string("", 2025) is None


class TestExtractMovieMetadataFromHtml:
    def test_extracts_metadata_from_movie_detail_page(self):
        from movies_app.tasks.mamm_download_task import _extract_movie_metadata_from_html

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "elmamm_org_single_movie.html",
        )

        with open(html_snapshot_path, encoding="utf-8") as f:
            html_content = f.read()

        metadata = _extract_movie_metadata_from_html(html_content)

        assert metadata is not None
        assert metadata.title != ""

    def test_returns_none_for_empty_html(self):
        from movies_app.tasks.mamm_download_task import _extract_movie_metadata_from_html

        metadata = _extract_movie_metadata_from_html("<html></html>")
        assert metadata is None


@pytest.mark.django_db
class TestSaveShowtimesFromHtml:
    def test_saves_showtimes_from_html(self, mamm_theater):
        from movies_app.models import Showtime
        from movies_app.tasks.mamm_download_task import save_showtimes_from_html

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "elmamm_org_semana",
        )

        with open(html_snapshot_path, encoding="utf-8") as f:
            html_content = f.read()

        report = save_showtimes_from_html(html_content, mamm_theater)

        assert report.total_showtimes > 0
        assert Showtime.objects.filter(theater=mamm_theater).exists()

    def test_creates_theater_if_not_provided(self):
        from movies_app.models import Theater
        from movies_app.tasks.mamm_download_task import _get_or_create_mamm_theater

        theater = _get_or_create_mamm_theater()

        assert theater is not None
        assert theater.slug == "mamm"
        assert theater.name == "MAMM - Museo de Arte Moderno de Medellín"

        theater_from_db = Theater.objects.get(slug="mamm")
        assert theater_from_db == theater


@pytest.fixture
def mamm_theater():
    from movies_app.models import Theater

    theater, _ = Theater.objects.get_or_create(
        slug="mamm",
        defaults={
            "name": "MAMM - Test Theater",
            "chain": "MAMM",
            "address": "Test Address",
            "city": "Medellín",
            "neighborhood": "Test",
            "website": "https://www.elmamm.org/cine/",
            "screen_count": 1,
            "is_active": True,
        },
    )
    return theater
