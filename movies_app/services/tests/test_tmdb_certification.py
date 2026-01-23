from unittest.mock import MagicMock, patch

from movies_app.services.tmdb_service import TMDBService


class TestExtractCertification:
    """Tests for TMDBService._extract_certification method."""

    def _create_tmdb_service(self):
        mock_settings = MagicMock()
        mock_settings.TMDB_READ_ACCESS_TOKEN = "fake_token"
        with patch("movies_app.services.tmdb_service.settings", mock_settings):
            return TMDBService()

    def test_extracts_us_certification(self):
        tmdb_service = self._create_tmdb_service()
        release_dates_data = {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [
                        {"certification": "PG-13", "type": 3, "release_date": "2024-01-15"}
                    ],
                },
                {
                    "iso_3166_1": "GB",
                    "release_dates": [
                        {"certification": "12A", "type": 3, "release_date": "2024-01-15"}
                    ],
                },
            ]
        }
        result = tmdb_service._extract_certification(release_dates_data)
        assert result == "PG-13"

    def test_prefers_us_over_co(self):
        tmdb_service = self._create_tmdb_service()
        release_dates_data = {
            "results": [
                {
                    "iso_3166_1": "CO",
                    "release_dates": [
                        {"certification": "+12", "type": 3, "release_date": "2024-01-15"}
                    ],
                },
                {
                    "iso_3166_1": "US",
                    "release_dates": [
                        {"certification": "PG-13", "type": 3, "release_date": "2024-01-15"}
                    ],
                },
            ]
        }
        result = tmdb_service._extract_certification(release_dates_data)
        assert result == "PG-13"

    def test_uses_co_when_no_us(self):
        tmdb_service = self._create_tmdb_service()
        release_dates_data = {
            "results": [
                {
                    "iso_3166_1": "CO",
                    "release_dates": [
                        {"certification": "+12", "type": 3, "release_date": "2024-01-15"}
                    ],
                },
                {
                    "iso_3166_1": "GB",
                    "release_dates": [
                        {"certification": "12A", "type": 3, "release_date": "2024-01-15"}
                    ],
                },
            ]
        }
        result = tmdb_service._extract_certification(release_dates_data)
        assert result == "+12"

    def test_uses_first_available_when_no_us_or_co(self):
        tmdb_service = self._create_tmdb_service()
        release_dates_data = {
            "results": [
                {
                    "iso_3166_1": "GB",
                    "release_dates": [
                        {"certification": "12A", "type": 3, "release_date": "2024-01-15"}
                    ],
                },
            ]
        }
        result = tmdb_service._extract_certification(release_dates_data)
        assert result == "12A"

    def test_returns_none_when_empty_results(self):
        tmdb_service = self._create_tmdb_service()
        release_dates_data = {"results": []}
        result = tmdb_service._extract_certification(release_dates_data)
        assert result is None

    def test_ignores_empty_certification(self):
        tmdb_service = self._create_tmdb_service()
        release_dates_data = {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [
                        {"certification": "", "type": 3, "release_date": "2024-01-15"}
                    ],
                },
                {
                    "iso_3166_1": "GB",
                    "release_dates": [
                        {"certification": "12A", "type": 3, "release_date": "2024-01-15"}
                    ],
                },
            ]
        }
        result = tmdb_service._extract_certification(release_dates_data)
        assert result == "12A"

    def test_only_considers_theatrical_and_premiere_types(self):
        tmdb_service = self._create_tmdb_service()
        release_dates_data = {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [
                        {"certification": "R", "type": 4, "release_date": "2024-01-15"},  # Digital
                        {"certification": "PG-13", "type": 3, "release_date": "2024-01-10"},  # Theatrical
                    ],
                },
            ]
        }
        result = tmdb_service._extract_certification(release_dates_data)
        assert result == "PG-13"

    def test_accepts_premiere_type(self):
        tmdb_service = self._create_tmdb_service()
        release_dates_data = {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [
                        {"certification": "PG-13", "type": 1, "release_date": "2024-01-15"}  # Premiere
                    ],
                },
            ]
        }
        result = tmdb_service._extract_certification(release_dates_data)
        assert result == "PG-13"

    def test_strips_whitespace(self):
        tmdb_service = self._create_tmdb_service()
        release_dates_data = {
            "results": [
                {
                    "iso_3166_1": "US",
                    "release_dates": [
                        {"certification": "  PG-13  ", "type": 3, "release_date": "2024-01-15"}
                    ],
                },
            ]
        }
        result = tmdb_service._extract_certification(release_dates_data)
        assert result == "PG-13"
