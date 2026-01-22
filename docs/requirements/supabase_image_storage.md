# Supabase S3 Image Storage

## Problem

Movie images (posters and backdrops) are currently stored as TMDB URLs in the database:
- `poster_url`: e.g., `https://image.tmdb.org/t/p/w500/abc123.jpg`
- `backdrop_url`: e.g., `https://image.tmdb.org/t/p/w1280/xyz789.jpg`

Issues with external URLs:
1. **Dependency on TMDB**: If TMDB changes URLs or goes down, images break
2. **No control over caching**: Can't set our own CDN/caching policies
3. **Rate limiting**: TMDB may rate-limit image requests
4. **URL expiration**: External URLs could change or expire

## Solution

Download images from TMDB and store them in Supabase S3 storage. Store the Supabase URLs in the database instead.

## Supabase S3 Setup

### Bucket Configuration

Create a public bucket for movie images:
- **Bucket name**: `movie-images`
- **Public access**: Yes (images need to be publicly accessible)
- **File structure**:
  ```
  movie-images/
  ├── posters/
  │   └── {tmdb_id}.jpg
  └── backdrops/
      └── {tmdb_id}.jpg
  ```

### Environment Variables

```bash
SUPABASE_URL=https://xxxx.supabase.co
SUPABASE_SERVICE_KEY=eyJhbGc...  # Service role key for server-side uploads
SUPABASE_BUCKET_NAME=movie-images
```

## Implementation

### 1. Supabase Storage Service

Create `movies_app/services/supabase_storage_service.py`:

```python
class SupabaseStorageService:
    def __init__(self, url: str, service_key: str, bucket_name: str):
        self.client = create_client(url, service_key)
        self.bucket_name = bucket_name

    def upload_image(self, image_bytes: bytes, path: str) -> str:
        """Upload image and return public URL."""
        ...

    def download_and_upload_from_url(self, source_url: str, dest_path: str) -> str:
        """Download from URL and upload to Supabase, return new URL."""
        ...

    def delete_image(self, path: str) -> None:
        """Delete an image from storage."""
        ...

    def image_exists(self, path: str) -> bool:
        """Check if image already exists in storage."""
        ...
```

### 2. Model Changes

Add new fields to `Movie` model to track Supabase storage:

```python
# Option A: Replace existing fields (breaking change)
poster_url = models.URLField(...)  # Now stores Supabase URL

# Option B: Add new fields (backwards compatible)
poster_supabase_url = models.URLField(
    max_length=500,
    blank=True,
    default="",
    help_text="Supabase storage URL for poster",
)
backdrop_supabase_url = models.URLField(
    max_length=500,
    blank=True,
    default="",
    help_text="Supabase storage URL for backdrop",
)
```

**Recommendation**: Option A (replace) since this is an internal tool with no backwards compatibility concerns.

### 3. Integration Points

#### A. During Movie Creation

In `_get_or_create_movie()` after getting TMDB details:

```python
# After fetching TMDB data
if tmdb_details.poster_path:
    tmdb_poster_url = f"https://image.tmdb.org/t/p/w500{tmdb_details.poster_path}"
    poster_url = storage_service.download_and_upload_from_url(
        source_url=tmdb_poster_url,
        dest_path=f"posters/{tmdb_details.id}.jpg"
    )

if tmdb_details.backdrop_path:
    tmdb_backdrop_url = f"https://image.tmdb.org/t/p/w1280{tmdb_details.backdrop_path}"
    backdrop_url = storage_service.download_and_upload_from_url(
        source_url=tmdb_backdrop_url,
        dest_path=f"backdrops/{tmdb_details.id}.jpg"
    )
```

#### B. Management Command for Existing Movies

Create `upload_existing_images_to_supabase` command:

```python
# For each movie with TMDB URLs but no Supabase URLs:
# 1. Download from TMDB
# 2. Upload to Supabase
# 3. Update movie record
```

### 4. Image Sizes

TMDB image size options:
- **Posters**: `w92`, `w154`, `w185`, `w342`, `w500`, `w780`, `original`
- **Backdrops**: `w300`, `w780`, `w1280`, `original`

**Recommendation**:
- Posters: `w500` (good balance of quality and size, ~50-100KB)
- Backdrops: `w1280` (high quality for hero images, ~100-300KB)

### 5. Error Handling

Handle failures gracefully:
- If Supabase upload fails, keep TMDB URL as fallback
- Log errors but don't block movie creation
- Create `OperationalIssue` for tracking

```python
try:
    poster_url = storage_service.download_and_upload_from_url(...)
except SupabaseUploadError as e:
    logger.error(f"Failed to upload poster: {e}")
    OperationalIssue.objects.create(
        issue_type="Supabase Upload Failed",
        description=f"Movie: {movie_title}, Error: {e}",
    )
    poster_url = tmdb_poster_url  # Fallback to TMDB URL
```

## Dependencies

```toml
# pyproject.toml
[project.dependencies]
supabase = ">=2.0.0"
```

## Testing

### Unit Tests

1. `SupabaseStorageService.upload_image` uploads correctly
2. `SupabaseStorageService.download_and_upload_from_url` handles TMDB URLs
3. `SupabaseStorageService.image_exists` returns correct boolean
4. Error handling when upload fails

### Integration Tests

1. Movie creation uploads images to Supabase
2. Fallback to TMDB URL when Supabase fails
3. Management command migrates existing movies

### Mocking Strategy

Mock `supabase` client in tests to avoid real API calls:

```python
@pytest.fixture
def mock_supabase_storage():
    with patch("movies_app.services.supabase_storage_service.create_client") as mock:
        yield mock
```

## Migration Plan

1. **Phase 1**: Add Supabase service and new fields
2. **Phase 2**: Update scraper to upload images for new movies
3. **Phase 3**: Run management command to migrate existing movies
4. **Phase 4**: (Optional) Remove TMDB URL fallback logic

## Cost Considerations

Supabase free tier includes:
- 1GB storage
- 2GB bandwidth/month

Estimated usage:
- ~500 movies × (100KB poster + 200KB backdrop) = ~150MB storage
- Well within free tier limits

## Security

- Use service role key (not anon key) for uploads
- Service key stored in environment variable, never committed
- Bucket is public read, but only server can write
