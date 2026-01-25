import pytest

from movies_app.models import OperationalIssue, Showtime
from movies_app.tasks.download_utilities import normalize_translation_type


@pytest.mark.django_db
class TestNormalizeTranslationType:
    def test_normalizes_doblada(self):
        result = normalize_translation_type(
            "Doblada",
            task="test_task",
            context={"test": "context"},
        )
        assert result == Showtime.TranslationType.DOBLADA

    def test_normalizes_doblada_uppercase(self):
        result = normalize_translation_type(
            "DOBLADA",
            task="test_task",
            context={"test": "context"},
        )
        assert result == Showtime.TranslationType.DOBLADA

    def test_normalizes_subtitulada(self):
        result = normalize_translation_type(
            "Subtitulada",
            task="test_task",
            context={"test": "context"},
        )
        assert result == Showtime.TranslationType.SUBTITULADA

    def test_normalizes_subtitulada_uppercase(self):
        result = normalize_translation_type(
            "SUBTITULADA",
            task="test_task",
            context={"test": "context"},
        )
        assert result == Showtime.TranslationType.SUBTITULADA

    def test_normalizes_masculine_doblado_to_doblada(self):
        result = normalize_translation_type(
            "Doblado",
            task="test_task",
            context={"test": "context"},
        )
        assert result == Showtime.TranslationType.DOBLADA

    def test_normalizes_masculine_subtitulado_to_subtitulada(self):
        result = normalize_translation_type(
            "Subtitulado",
            task="test_task",
            context={"test": "context"},
        )
        assert result == Showtime.TranslationType.SUBTITULADA

    def test_normalizes_original(self):
        result = normalize_translation_type(
            "Original",
            task="test_task",
            context={"test": "context"},
        )
        assert result == Showtime.TranslationType.ORIGINAL

    def test_empty_value_returns_empty(self):
        result = normalize_translation_type(
            "",
            task="test_task",
            context={"test": "context"},
        )
        assert result == ""

    def test_unknown_value_returns_empty_and_creates_operational_issue(self):
        initial_count = OperationalIssue.objects.count()

        result = normalize_translation_type(
            "UNKNOWN_VALUE",
            task="test_task",
            context={"theater": "Test Theater", "movie": "Test Movie"},
        )

        assert result == ""
        assert OperationalIssue.objects.count() == initial_count + 1

        issue = OperationalIssue.objects.latest("created_at")
        assert issue.task == "test_task"
        assert "UNKNOWN_VALUE" in issue.error_message
        assert issue.context["theater"] == "Test Theater"
        assert issue.context["movie"] == "Test Movie"
        assert issue.severity == OperationalIssue.Severity.WARNING

    def test_invalid_value_creates_operational_issue(self):
        initial_count = OperationalIssue.objects.count()

        normalize_translation_type(
            "INVALID",
            task="cineprox_download_task",
            context={"theater": "Test Theater", "movie": "Test Movie"},
        )

        assert OperationalIssue.objects.count() == initial_count + 1

        issue = OperationalIssue.objects.latest("created_at")
        assert "INVALID" in issue.error_message
        assert issue.context["theater"] == "Test Theater"
        assert issue.context["movie"] == "Test Movie"
