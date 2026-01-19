from django.db import models


class Theater(models.Model):
    """Represents a movie theater/cinema location."""

    name = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True)
    chain = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=300)
    city = models.CharField(max_length=100, default="Medellín")
    neighborhood = models.CharField(max_length=100, blank=True)
    latitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    longitude = models.DecimalField(max_digits=9, decimal_places=6, null=True, blank=True)
    phone = models.CharField(max_length=50, blank=True)
    screen_count = models.PositiveIntegerField(null=True, blank=True)
    website = models.URLField(blank=True)
    colombia_dot_com_url = models.URLField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["city"]),
            models.Index(fields=["chain"]),
            models.Index(fields=["is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.name} - {self.city}"
