"""
API Call Counter model for tracking external API usage per day.
"""

import datetime

from django.db import models
from django.db.models import F, Sum


class APICallCounter(models.Model):
    """
    Tracks the number of calls made to external APIs per day.

    Each row represents calls to a specific service on a specific date.
    """

    service_name = models.CharField(
        max_length=100,
        help_text="Name of the external service (e.g., 'tmdb')",
    )
    date = models.DateField(
        help_text="Date of the API calls",
    )
    call_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of API calls made on this date",
    )
    last_called_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of the last API call on this date",
    )

    class Meta:
        verbose_name = "API Call Counter"
        verbose_name_plural = "API Call Counters"
        constraints = [
            models.UniqueConstraint(
                fields=["service_name", "date"],
                name="unique_service_date",
            )
        ]
        indexes = [
            models.Index(fields=["service_name", "date"]),
        ]

    def __str__(self):
        return f"{self.service_name} ({self.date}): {self.call_count} calls"

    @classmethod
    def increment(cls, service_name: str) -> int:
        """
        Increment the call count for a service for today and return the new count.

        Uses atomic update to handle concurrent calls safely.
        """
        from django.utils import timezone

        today = timezone.now().date()

        counter, _ = cls.objects.get_or_create(
            service_name=service_name,
            date=today,
            defaults={"call_count": 0},
        )

        cls.objects.filter(pk=counter.pk).update(
            call_count=F("call_count") + 1,
            last_called_at=timezone.now(),
        )

        counter.refresh_from_db()
        return counter.call_count

    @classmethod
    def get_daily_counts(
        cls,
        service_name: str,
        start_date: datetime.date,
        end_date: datetime.date,
    ) -> list[dict[str, datetime.date | int]]:
        """
        Get daily call counts for a service within a date range.

        Returns a list of dicts with 'date' and 'call_count' keys.
        """
        return list(
            cls.objects.filter(
                service_name=service_name,
                date__gte=start_date,
                date__lte=end_date,
            )
            .values("date")
            .annotate(total=Sum("call_count"))
            .order_by("date")
        )

    @classmethod
    def get_total_calls(
        cls,
        service_name: str,
        start_date: datetime.date | None,
        end_date: datetime.date | None,
    ) -> int:
        """
        Get total call count for a service, optionally within a date range.
        """
        queryset = cls.objects.filter(service_name=service_name)

        if start_date:
            queryset = queryset.filter(date__gte=start_date)
        if end_date:
            queryset = queryset.filter(date__lte=end_date)

        result = queryset.aggregate(total=Sum("call_count"))
        return result["total"] or 0
