from dataclasses import dataclass
from movies_app.models import Movie

@dataclass
class MovieLookupResult:
    """Result of attempting to find or create a movie."""
    movie: Movie | None
    is_new: bool
    tmdb_called: bool
