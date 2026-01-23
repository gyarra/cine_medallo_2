from movies_app.services.tmdb_service import (
    TMDBGenre,
    TMDBMovieDetails,
    TMDBProductionCompany,
    TMDBVideo,
)


def _create_video(
    key: str,
    iso_639_1: str = "en",
    official: bool = True,
    size: int = 1080,
    video_type: str = "Trailer",
    site: str = "YouTube",
) -> TMDBVideo:
    """Helper to create TMDBVideo instances for tests."""
    return TMDBVideo(
        id=f"id_{key}",
        key=key,
        name=f"Video {key}",
        site=site,
        size=size,
        type=video_type,
        official=official,
        iso_639_1=iso_639_1,
        iso_3166_1="US",
        published_at="2024-01-01T00:00:00.000Z",
    )


def _create_movie_details(videos: list[TMDBVideo] | None) -> TMDBMovieDetails:
    """Helper to create TMDBMovieDetails with specified videos."""
    return TMDBMovieDetails(
        id=123,
        title="Test Movie",
        original_title="Test Movie",
        overview="Test overview",
        release_date="2024-01-15",
        popularity=100.0,
        vote_average=7.5,
        vote_count=1000,
        poster_path="/poster.jpg",
        backdrop_path="/backdrop.jpg",
        genres=[TMDBGenre(id=28, name="Acción")],
        original_language="en",
        adult=False,
        video=False,
        runtime=120,
        budget=100000000,
        revenue=500000000,
        status="Released",
        tagline="Test tagline",
        homepage="https://example.com",
        imdb_id="tt1234567",
        production_companies=[
            TMDBProductionCompany(id=1, name="Test Studio", logo_path=None, origin_country="US")
        ],
        cast=None,
        crew=None,
        videos=videos,
        certification=None,
    )


class TestGetBestTrailer:
    def test_returns_none_when_no_videos(self):
        details = _create_movie_details(videos=None)
        assert details.get_best_trailer() is None

    def test_returns_none_when_empty_videos(self):
        details = _create_movie_details(videos=[])
        assert details.get_best_trailer() is None

    def test_returns_none_when_no_trailers(self):
        videos = [
            _create_video("teaser1", video_type="Teaser"),
            _create_video("clip1", video_type="Clip"),
        ]
        details = _create_movie_details(videos=videos)
        assert details.get_best_trailer() is None

    def test_returns_none_when_no_youtube_trailers(self):
        videos = [
            _create_video("vimeo1", site="Vimeo"),
        ]
        details = _create_movie_details(videos=videos)
        assert details.get_best_trailer() is None

    def test_prefers_spanish_over_english(self):
        videos = [
            _create_video("english", iso_639_1="en", official=True, size=1080),
            _create_video("spanish", iso_639_1="es", official=True, size=1080),
        ]
        details = _create_movie_details(videos=videos)
        best = details.get_best_trailer()
        assert best is not None
        assert best.key == "spanish"
        assert best.iso_639_1 == "es"

    def test_prefers_official_over_unofficial(self):
        videos = [
            _create_video("unofficial", iso_639_1="es", official=False, size=1080),
            _create_video("official", iso_639_1="es", official=True, size=720),
        ]
        details = _create_movie_details(videos=videos)
        best = details.get_best_trailer()
        assert best is not None
        assert best.key == "official"

    def test_prefers_higher_quality(self):
        videos = [
            _create_video("low_quality", iso_639_1="es", official=True, size=480),
            _create_video("high_quality", iso_639_1="es", official=True, size=1080),
        ]
        details = _create_movie_details(videos=videos)
        best = details.get_best_trailer()
        assert best is not None
        assert best.key == "high_quality"
        assert best.size == 1080

    def test_spanish_unofficial_beats_english_official(self):
        videos = [
            _create_video("english_official", iso_639_1="en", official=True, size=1080),
            _create_video("spanish_unofficial", iso_639_1="es", official=False, size=1080),
        ]
        details = _create_movie_details(videos=videos)
        best = details.get_best_trailer()
        assert best is not None
        assert best.key == "spanish_unofficial"

    def test_falls_back_to_english_when_no_spanish(self):
        videos = [
            _create_video("french", iso_639_1="fr", official=True, size=1080),
            _create_video("english", iso_639_1="en", official=True, size=1080),
        ]
        details = _create_movie_details(videos=videos)
        best = details.get_best_trailer()
        assert best is not None
        assert best.key == "english"

    def test_youtube_url_property(self):
        video = _create_video("abc123")
        assert video.youtube_url == "https://www.youtube.com/watch?v=abc123"

    def test_youtube_url_returns_none_for_non_youtube(self):
        video = _create_video("abc123", site="Vimeo")
        assert video.youtube_url is None

    def test_complex_selection_scenario(self):
        """Test with a realistic mix of videos."""
        videos = [
            _create_video("en_teaser", iso_639_1="en", video_type="Teaser", official=True, size=1080),
            _create_video("en_trailer_720", iso_639_1="en", official=True, size=720),
            _create_video("es_trailer_unofficial", iso_639_1="es", official=False, size=1080),
            _create_video("en_trailer_1080", iso_639_1="en", official=True, size=1080),
            _create_video("es_trailer_official", iso_639_1="es", official=True, size=720),
        ]
        details = _create_movie_details(videos=videos)
        best = details.get_best_trailer()
        assert best is not None
        # Spanish official should win over Spanish unofficial (despite lower size)
        assert best.key == "es_trailer_official"
