import datetime
import os
from unittest.mock import MagicMock, patch

import pytest

from movies_app.models import Movie, OperationalIssue, Showtime
from movies_app.services.tmdb_service import (
    TMDBGenre,
    TMDBMovieDetails,
    TMDBMovieResult,
    TMDBProductionCompany,
    TMDBSearchResponse,
)
from movies_app.tasks.download_utilities import BOGOTA_TZ, parse_time_string
from movies_app.tasks.mamm_download_task import (
    MAMMScraperAndHTMLParser,
    MAMMShowtimeSaver,
)


class TestParseShowtimesFromWeeklyScheduleHtml:
    def test_extracts_showtimes_from_mamm_schedule_html(self):
        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "elmamm_org_semana",
        )

        with open(html_snapshot_path, encoding="utf-8") as f:
            html_content = f.read()

        showtimes = MAMMScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html_content)

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

        showtimes = MAMMScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html_content)

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

        showtimes = MAMMScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html_content)

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

        showtimes = MAMMScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html_content)

        labeled_showtimes = [st for st in showtimes if st.special_label]
        assert len(labeled_showtimes) > 0

        labels = {st.special_label for st in labeled_showtimes}
        assert "Remasterizada en 4K" in labels or "Exclusivo Cine MAMM" in labels


class TestParseTimeString:
    def test_parses_pm_times(self):
        assert parse_time_string("2:00 pm") == datetime.time(14, 0)
        assert parse_time_string("9:30 pm") == datetime.time(21, 30)
        assert parse_time_string("12:00 pm") == datetime.time(12, 0)

    def test_parses_am_times(self):
        assert parse_time_string("10:00 am") == datetime.time(10, 0)
        assert parse_time_string("12:00 am") == datetime.time(0, 0)

    def test_parses_times_with_periods(self):
        assert parse_time_string("2:00 p.m.") == datetime.time(14, 0)
        assert parse_time_string("10:30 a.m.") == datetime.time(10, 30)

    def test_returns_none_for_invalid_time(self):
        assert parse_time_string("invalid") is None
        assert parse_time_string("") is None


class TestParseDateString:
    def test_parses_spanish_dates(self):
        assert MAMMScraperAndHTMLParser._parse_date_string("viernes 23 Ene", 2025) == datetime.date(2025, 1, 23)
        assert MAMMScraperAndHTMLParser._parse_date_string("sábado 24 Ene", 2025) == datetime.date(2025, 1, 24)
        assert MAMMScraperAndHTMLParser._parse_date_string("domingo 25 Ene", 2025) == datetime.date(2025, 1, 25)

    def test_parses_different_months(self):
        assert MAMMScraperAndHTMLParser._parse_date_string("15 Feb", 2025) == datetime.date(2025, 2, 15)
        assert MAMMScraperAndHTMLParser._parse_date_string("1 Dic", 2025) == datetime.date(2025, 12, 1)
        assert MAMMScraperAndHTMLParser._parse_date_string("31 Jul", 2025) == datetime.date(2025, 7, 31)

    def test_returns_none_for_invalid_date(self):
        assert MAMMScraperAndHTMLParser._parse_date_string("invalid", 2025) is None
        assert MAMMScraperAndHTMLParser._parse_date_string("", 2025) is None


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

            showtimes = MAMMScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html)

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

            showtimes = MAMMScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html)

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

            showtimes = MAMMScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(html)

        assert len(showtimes) == 1
        assert showtimes[0].date == datetime.date(2025, 12, 28)


class TestParseMovieMetaFromMovieHtml:
    def test_extracts_metadata_from_movie_detail_page(self):
        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "elmamm_org_single_movie.html",
        )

        with open(html_snapshot_path, encoding="utf-8") as f:
            html_content = f.read()

        metadata = MAMMScraperAndHTMLParser.parse_movie_meta_from_movie_html(html_content)

        assert metadata is not None
        assert metadata.title != ""

    def test_returns_none_for_empty_html(self):
        metadata = MAMMScraperAndHTMLParser.parse_movie_meta_from_movie_html("<html></html>")
        assert metadata is None


@pytest.fixture
def mock_tmdb_service() -> MagicMock:
    """Create a mock TMDB service that returns valid search results."""
    tmdb_service = MagicMock()
    tmdb_service.search_movie.return_value = TMDBSearchResponse(
        page=1,
        total_pages=1,
        total_results=1,
        results=[
            TMDBMovieResult(
                id=12345,
                title="Test Movie",
                original_title="Test Movie",
                overview="A test movie",
                release_date="2025-01-01",
                popularity=100.0,
                vote_average=7.0,
                vote_count=500,
                poster_path="/test.jpg",
                backdrop_path="/test_backdrop.jpg",
                genre_ids=[28],
                original_language="en",
                adult=False,
                video=False,
            ),
        ],
    )
    tmdb_service.get_movie_details.return_value = TMDBMovieDetails(
        id=12345,
        title="Test Movie",
        original_title="Test Movie",
        overview="A test movie",
        release_date="2025-01-01",
        popularity=100.0,
        vote_average=7.0,
        vote_count=500,
        poster_path="/test.jpg",
        backdrop_path="/test_backdrop.jpg",
        genres=[TMDBGenre(id=28, name="Acción")],
        original_language="en",
        adult=False,
        video=False,
        runtime=120,
        budget=0,
        revenue=0,
        status="Released",
        tagline="",
        homepage="",
        imdb_id="tt1234567",
        production_companies=[
            TMDBProductionCompany(id=1, name="Test Studio", logo_path=None, origin_country="US")
        ],
        cast=None,
        crew=None,
        videos=None,
        certification="PG",
    )
    return tmdb_service


def _create_saver_with_mocked_scraper(html_content: str, mock_tmdb_service: MagicMock) -> MAMMShowtimeSaver:
    """Create a MAMMShowtimeSaver with a mocked scraper that returns the given HTML."""
    scraper = MagicMock(spec=MAMMScraperAndHTMLParser)
    scraper.download_weekly_schedule.return_value = html_content
    scraper.parse_showtimes_from_weekly_schedule_html.side_effect = (
        MAMMScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html
    )
    scraper.download_individual_movie_html.return_value = "<html></html>"
    scraper.parse_movie_meta_from_movie_html.return_value = None

    return MAMMShowtimeSaver(scraper, mock_tmdb_service, storage_service=None)


@pytest.mark.django_db
class TestMAMMShowtimeSaverExecute:
    def test_saves_showtimes_from_html(self, mamm_theater, mock_tmdb_service):
        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "elmamm_org_semana",
        )

        with open(html_snapshot_path, encoding="utf-8") as f:
            html_content = f.read()

        saver = _create_saver_with_mocked_scraper(html_content, mock_tmdb_service)
        report = saver.execute()

        assert report.total_showtimes > 0
        assert Showtime.objects.filter(theater=mamm_theater).exists()

    def test_deletes_existing_showtimes_for_date_and_adds_new_ones(self, mamm_theater, mock_tmdb_service):
        """Verify that existing showtimes are deleted before new ones are added."""
        movie = Movie.objects.create(
            title_es="Old Test Movie",
            slug="old-test-movie",
            original_title="Old Test Movie",
            year=2025,
        )

        target_date = datetime.date(2025, 1, 24)
        other_date = datetime.date(2025, 1, 25)

        for hour in [14, 16, 18]:
            Showtime.objects.create(
                theater=mamm_theater,
                movie=movie,
                start_date=target_date,
                start_time=datetime.time(hour, 0),
                format="Old Format",
                source_url="https://old-url.com",
            )

        Showtime.objects.create(
            theater=mamm_theater,
            movie=movie,
            start_date=other_date,
            start_time=datetime.time(20, 0),
            format="Other Date Format",
            source_url="https://other-url.com",
        )

        assert Showtime.objects.filter(theater=mamm_theater, start_date=target_date).count() == 3
        assert Showtime.objects.filter(theater=mamm_theater, start_date=other_date).count() == 1

        mock_now = datetime.datetime(2025, 1, 24, 12, 0, 0, tzinfo=BOGOTA_TZ)
        html_content = """
        <html>
        <body>
        <section class="schedule-week">
            <div class="col">
                <div class="day">
                    <p class="small">viernes 24 Ene</p>
                </div>
                <div class="card">
                    <a href="https://www.elmamm.org/producto/new-movie/">
                        <p class="small">7:00 pm</p>
                        <h3>New Movie Title</h3>
                    </a>
                </div>
                <div class="card">
                    <a href="https://www.elmamm.org/producto/another-movie/">
                        <p class="small">9:30 pm</p>
                        <h3>Another New Movie</h3>
                    </a>
                </div>
            </div>
        </section>
        </body>
        </html>
        """

        with patch("movies_app.tasks.mamm_download_task.datetime") as mock_datetime:
            mock_datetime.datetime.now.return_value = mock_now
            mock_datetime.date = datetime.date
            mock_datetime.time = datetime.time

            saver = _create_saver_with_mocked_scraper(html_content, mock_tmdb_service)
            saver.execute()

        target_date_showtimes = Showtime.objects.filter(
            theater=mamm_theater, start_date=target_date
        )
        assert target_date_showtimes.count() == 2

        showtime_times = {st.start_time for st in target_date_showtimes}
        assert datetime.time(19, 0) in showtime_times
        assert datetime.time(21, 30) in showtime_times

        assert not target_date_showtimes.filter(format="Old Format").exists()

        other_date_showtimes = Showtime.objects.filter(
            theater=mamm_theater, start_date=other_date
        )
        assert other_date_showtimes.count() == 1
        other_date_showtime = other_date_showtimes.first()
        assert other_date_showtime is not None
        assert other_date_showtime.format == "Other Date Format"


@pytest.mark.django_db
class TestParseShowtimesOperationalIssues:
    def test_creates_operational_issue_for_unparseable_time(self):
        html_with_invalid_time = """
        <html>
        <body>
        <section class="schedule-week">
            <div class="col">
                <div class="day">
                    <p class="small">viernes 20 Ene</p>
                </div>
                <div class="card">
                    <a href="https://www.elmamm.org/producto/test-movie/">
                        <p class="small">INVALID_TIME</p>
                        <h3>Test Movie</h3>
                    </a>
                </div>
            </div>
        </section>
        </body>
        </html>
        """
        initial_count = OperationalIssue.objects.count()

        showtimes = MAMMScraperAndHTMLParser.parse_showtimes_from_weekly_schedule_html(
            html_with_invalid_time
        )

        assert len(showtimes) == 0
        assert OperationalIssue.objects.count() == initial_count + 1

        issue = OperationalIssue.objects.latest("created_at")
        assert issue.name == "Time Parse Failed"
        assert issue.task == "mamm_download_task"
        assert "INVALID_TIME" in issue.error_message
        assert issue.context["movie"] == "Test Movie"
        assert issue.severity == OperationalIssue.Severity.WARNING


# mamm_theater fixture is now in conftest.py
