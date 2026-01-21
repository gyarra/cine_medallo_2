"""Add slug field to Movie model."""

from django.db import migrations, models
from django.utils.text import slugify


def populate_slugs(apps, schema_editor):
    """Generate unique slugs for existing movies."""
    Movie = apps.get_model("movies_app", "Movie")
    for movie in Movie.objects.all():
        base_slug = slugify(movie.title_es)
        if not base_slug:
            base_slug = f"movie-{movie.pk}"
        slug = base_slug
        counter = 1
        while Movie.objects.filter(slug=slug).exclude(pk=movie.pk).exists():
            slug = f"{base_slug}-{counter}"
            counter += 1
        movie.slug = slug
        movie.save(update_fields=["slug"])


def reverse_populate_slugs(apps, schema_editor):
    """No-op reverse migration."""
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("movies_app", "0004_add_showtime_model"),
    ]

    operations = [
        # Step 1: Add slug field with null=True temporarily (use CharField to avoid index creation)
        migrations.AddField(
            model_name="movie",
            name="slug",
            field=models.CharField(
                max_length=350,
                null=True,
                help_text="URL-friendly identifier",
            ),
        ),
        # Step 2: Populate slugs for existing movies
        migrations.RunPython(populate_slugs, reverse_populate_slugs),
        # Step 3: Convert to SlugField with unique constraint
        migrations.AlterField(
            model_name="movie",
            name="slug",
            field=models.SlugField(
                max_length=350,
                unique=True,
                help_text="URL-friendly identifier",
            ),
        ),
    ]
