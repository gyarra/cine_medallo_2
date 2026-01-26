# Identifying System Issues

Use these Django ORM queries to diagnose problems in the movie scraping pipeline.

## Operational Issues

### Recent Issues by Name
```python
from django.db.models import Count
from django.utils import timezone
from datetime import timedelta
from movies_app.models import OperationalIssue

OperationalIssue.objects.filter(
    created_at__gte=timezone.now() - timedelta(hours=24)
).values('name').annotate(
    count=Count('id')
).order_by('-count')
```

### Recent Issues by Task
```python
OperationalIssue.objects.filter(
    created_at__gte=timezone.now() - timedelta(hours=24)
).values('task', 'name').annotate(
    count=Count('id')
).order_by('-count')
```

### Issues by Severity
```python
OperationalIssue.objects.filter(
    created_at__gte=timezone.now() - timedelta(hours=24)
).values('severity').annotate(
    count=Count('id')
).order_by('-count')
```

### View Recent Issue Details
```python
for issue in OperationalIssue.objects.filter(
    created_at__gte=timezone.now() - timedelta(hours=24)
).order_by('-created_at')[:10]:
    print(f"{issue.name}: {issue.error_message}")
    print(f"  Context: {issue.context}")
    print()
```

## Movie Lookup Issues

### TMDB Year Mismatches
```python
OperationalIssue.objects.filter(
    name='TMDB Year Mismatch',
    created_at__gte=timezone.now() - timedelta(days=7)
).values('context__movie_name', 'context__source_year', 'context__tmdb_year').distinct()
```

### Unfindable Movies
```python
from movies_app.models import UnfindableMovieUrl

UnfindableMovieUrl.objects.values('reason', 'movie_title').annotate(
    count=Count('id')
).order_by('-count')
```

### Movies Without TMDB Match
```python
UnfindableMovieUrl.objects.filter(
    reason='no_tmdb_results'
).values('movie_title', 'url', 'attempts').order_by('-attempts')
```

## Showtime Issues

### Showtimes by Theater
```python
from movies_app.models import Showtime, Theater

Showtime.objects.values('theater__name').annotate(
    count=Count('id')
).order_by('-count')
```

### Recent Showtimes Created
```python
Showtime.objects.filter(
    created_at__gte=timezone.now() - timedelta(hours=24)
).values('theater__name').annotate(
    count=Count('id')
).order_by('-count')
```

### Showtimes Missing Movies
```python
Showtime.objects.filter(
    movie__isnull=True
).values('theater__name').annotate(
    count=Count('id')
).order_by('-count')
```

## Movie Data Quality

### Movies Without Poster
```python
from movies_app.models import Movie

Movie.objects.filter(
    poster_url__isnull=True
).values('title', 'tmdb_id')
```

### Movies Without Release Date
```python
Movie.objects.filter(
    release_date__isnull=True
).values('title', 'tmdb_id')
```

### Recent Movies Created
```python
Movie.objects.filter(
    created_at__gte=timezone.now() - timedelta(days=7)
).values('title', 'release_date', 'tmdb_id').order_by('-created_at')
```

## Theater Status

### All Theaters
```python
from movies_app.models import Theater

for theater in Theater.objects.all():
    showtime_count = theater.showtime_set.count()
    print(f"{theater.name}: {showtime_count} showtimes")
```

### Theaters Without Recent Showtimes
```python
from django.db.models import Max

Theater.objects.annotate(
    last_showtime=Max('showtime__start_time')
).filter(
    last_showtime__lt=timezone.now() - timedelta(days=7)
).values('name', 'last_showtime')
```

## Quick Health Checks

### Overall Counts
```python
from movies_app.models import Movie, Theater, Showtime, OperationalIssue

print(f"Theaters: {Theater.objects.count()}")
print(f"Movies: {Movie.objects.count()}")
print(f"Showtimes: {Showtime.objects.count()}")
print(f"Recent issues (24h): {OperationalIssue.objects.filter(created_at__gte=timezone.now() - timedelta(hours=24)).count()}")
```

### Error Rate Trend
```python
from django.db.models.functions import TruncHour

OperationalIssue.objects.filter(
    created_at__gte=timezone.now() - timedelta(hours=24)
).annotate(
    hour=TruncHour('created_at')
).values('hour').annotate(
    count=Count('id')
).order_by('hour')
```

## Running These Queries

Open Django shell:
```bash
source .venv/bin/activate
python manage.py shell
```

Then paste the query code.
