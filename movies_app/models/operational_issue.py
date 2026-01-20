from django.db import models


class OperationalIssue(models.Model):
    """Tracks errors and problems that occur during system operations."""

    class Severity(models.TextChoices):
        ERROR = "error", "Error"
        WARNING = "warning", "Warning"
        INFO = "info", "Info"

    name = models.CharField(max_length=255)
    task = models.CharField(max_length=255)
    error_message = models.TextField()
    traceback = models.TextField(blank=True)
    context = models.JSONField(default=dict, blank=True)
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.ERROR,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["created_at"]),
            models.Index(fields=["task"]),
            models.Index(fields=["severity"]),
        ]
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.task}) - {self.created_at}"
