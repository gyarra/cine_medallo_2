# Operational Issue Model

## Overview

The `OperationalIssue` model tracks errors, failures, and problems that occur during system operations. This provides visibility into issues without requiring log file access and enables tracking of recurring problems.


## Use Cases

1. **Task Failures** - Record when Celery tasks fail (e.g., scraping errors, API timeouts)
2. **External Service Errors** - Track failures from TMDB API, colombia.com scraping
3. **Data Quality Issues** - Log when expected data is missing or malformed
4. **Recurring Problem Detection** - Identify patterns in failures over time


## Fields

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `id` | AutoField | Yes | Primary key |
| `name` | CharField(255) | Yes | Short descriptive name (e.g., "TMDB API Error", "Scrape Timeout") |
| `task` | CharField(255) | Yes | Task or function where the issue occurred (e.g., "colombia_com_download_task", "save_showtimes_for_theater") |
| `error_message` | TextField | Yes | The exception message or error description |
| `traceback` | TextField | No | Full Python traceback if available |
| `context` | JSONField | No | Additional context data (theater_id, movie_name, URL, etc.) |
| `severity` | CharField(20) | Yes | One of: "error", "warning", "info" |
| `created_at` | DateTimeField | Yes | When the issue was recorded (auto_now_add) |


## Indexes

- `created_at` - For querying recent issues
- `task` - For filtering by task name
- `severity` - For filtering by severity level


## Example Usage

```python
OperationalIssue.objects.create(
    name="TMDB API Timeout",
    task="colombia_com_download_task",
    error_message="Connection timed out after 30 seconds",
    traceback="Traceback (most recent call last):\n  ...",
    context={"movie_name": "Avatar", "theater_id": 5},
    severity="error",
)
```


## Integration Points

1. **colombia_com_download_task** - Log scraping failures, missing date options
2. **_get_or_create_movie** - Log TMDB API errors
3. **save_showtimes_for_theater** - Log when no showtimes found for a theater


## Admin Interface

- List view with filters for: severity, task, date range
- Search by name and error_message


## Future Considerations

- Automatic deduplication of similar issues within a time window
- Email/Slack notifications for critical errors
- Retention policy to auto-delete old resolved issues
