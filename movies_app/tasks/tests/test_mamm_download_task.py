import datetime
import os
from unittest.mock import patch

import pytest

from movies_app.models import Showtime, Theater
from movies_app.tasks.mamm_download_task import (
    BOGOTA_TZ,
    _extract_movie_metadata_from_html,
    _extract_showtimes_from_html,
    _get_mamm_theater,
    _parse_date_string,
    _parse_time_string,
    save_showtimes_from_html,
)


class TestExtractShowtimesFromHtml:
    def test_extracts_showtimes_from_mamm_schedule_html(self):
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
        assert _parse_time_string("2:00 pm") == datetime.time(14, 0)
        assert _parse_time_string("9:30 pm") == datetime.time(21, 30)
        assert _parse_time_string("12:00 pm") == datetime.time(12, 0)

    def test_parses_am_times(self):
        assert _parse_time_string("10:00 am") == datetime.time(10, 0)
        assert _parse_time_string("12:00 am") == datetime.time(0, 0)

    def test_parses_times_with_periods(self):
        assert _parse_time_string("2:00 p.m.") == datetime.time(14, 0)
        assert _parse_time_string("10:30 a.m.") == datetime.time(10, 30)

    def test_returns_none_for_invalid_time(self):
        assert _parse_time_string("invalid") is None
        assert _parse_time_string("") is None


class TestParseDateString:
    def test_parses_spanish_dates(self):
        assert _parse_date_string("viernes 23 Ene", 2025) == datetime.date(2025, 1, 23)
        assert _parse_date_string("sábado 24 Ene", 2025) == datetime.date(2025, 1, 24)
        assert _parse_date_string("domingo 25 Ene", 2025) == datetime.date(2025, 1, 25)

    def test_parses_different_months(self):
        assert _parse_date_string("15 Feb", 2025) == datetime.date(2025, 2, 15)
        assert _parse_date_string("1 Dic", 2025) == datetime.date(2025, 12, 1)
        assert _parse_date_string("31 Jul", 2025) == datetime.date(2025, 7, 31)

    def test_returns_none_for_invalid_date(self):
        assert _parse_date_string("invalid", 2025) is None
        assert _parse_date_string("", 2025) is None


def _make_schedule_html(day_text: str) -> str:
    """Create minimal HTML for testing date parsing in _extract_showtimes_from_html."""
    return f"""
    <html>
    <body>
    <section class="schedule-week">
        <div class="col">
            <div class="day">
                <p class="small">{day_text}</p>
            </div>
            <div class="card">
                <a href="https://www.elmamm.org/producto/test-movie/">
                    <p class="small">7:00 pm</p>
                    <h3>Test Movie</h3>
                </a>
            </div>
        </div>
    </section>
    </body>
    </html>
    """


class TestYearBoundaryAdjustment:
    """Tests for the year boundary logic that adjusts dates crossing Dec/Jan."""

    def test_no_adjustment_when_date_is_within_normal_range(self):
        """When today is Jan 15 and we parse 'viernes 20 Ene', no adjustment needed."""
        mock_now = datetime.datetime(2027, 1, 15, 12, 0, 0, tzinfo=BOGOTA_TZ)
        html = _make_schedule_html("viernes 20 Ene")

        with patch("movies_app.tasks.mamm_download_task.datetime") as mock_datetime:
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date
            mock_datetime.time = datetime.time

            showtimes = _extract_showtimes_from_html(html)

        assert len(showtimes) == 1
        assert showtimes[0].date == datetime.date(2027, 1, 20)

    def test_increments_year_when_date_appears_far_in_past(self):
        """
        When today is Dec 28, 2025 and we parse '3 Jan', the initial parse gives
        3 Jan, 2025 which is in the past. Test that the years is adjusted correctly.
        """
        # Today is Dec 28, 2025
        mock_now = datetime.datetime(2025, 12, 28, 12, 0, 0, tzinfo=BOGOTA_TZ)
        # The schedule containes Jan 3
        html = _make_schedule_html("viernes 3 Ene")

        with patch("movies_app.tasks.mamm_download_task.datetime") as mock_datetime:
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date
            mock_datetime.time = datetime.time

            showtimes = _extract_showtimes_from_html(html)

        assert len(showtimes) == 1
        assert showtimes[0].date == datetime.date(2026, 1, 3)

    def test_decrements_year_when_date_appears_far_in_future(self):
        """
        When today is Jan 3, 2026 and we parse '28 Dic', the year should be 2025.
        """
        mock_now = datetime.datetime(2026, 1, 3, 12, 0, 0, tzinfo=BOGOTA_TZ)
        html = _make_schedule_html("domingo 28 Dic")

        with patch("movies_app.tasks.mamm_download_task.datetime") as mock_datetime:
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date
            mock_datetime.time = datetime.time

            showtimes = _extract_showtimes_from_html(html)

        assert len(showtimes) == 1
        assert showtimes[0].date == datetime.date(2025, 12, 28)


class TestExtractMovieMetadataFromHtml:
    def test_extracts_metadata_from_movie_detail_page(self):
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
        metadata = _extract_movie_metadata_from_html("<html></html>")
        assert metadata is None


@pytest.mark.django_db
class TestSaveShowtimesFromHtml:
    def test_saves_showtimes_from_html(self, mamm_theater):
        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "elmamm_org_semana",
        )

        with open(html_snapshot_path, encoding="utf-8") as f:
            html_content = f.read()

        report = save_showtimes_from_html(html_content)

        assert report.total_showtimes > 0
        assert Showtime.objects.filter(theater=mamm_theater).exists()

    def test_raises_if_theater_not_found(self):
        Theater.objects.filter(slug="museo-de-arte-moderno-de-medellin").delete()

        with pytest.raises(Theater.DoesNotExist):
            _get_mamm_theater()


# mamm_theater fixture is now in conftest.py
