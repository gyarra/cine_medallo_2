import os


class TestExtractShowtimesFromHtml:
    def test_extracts_movie_names_from_colombia_dot_com_html(self):
        from movies_app.tasks.colombia_com_download_task import (
            _extract_showtimes_from_html,
        )

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "colombia_dot_com___vizcay_cine_colombia.html",
        )

        with open(html_snapshot_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        movie_showtimes = _extract_showtimes_from_html(html_content)
        movie_names = [ms.movie_name for ms in movie_showtimes]

        expected_movies = [
            "Avatar: Fuego Y Cenizas",
            "Exterminio: El Templo De Huesos",
            "Familia En Renta",
            "La Empleada",
            "La Única Opción",
            "Las Catadoras De Hitler",
            "Song Sung Blue: Sueño inquebrantable",
            "Valor Sentimental",
        ]

        assert movie_names == expected_movies

    def test_extracts_movie_urls_from_colombia_dot_com_html(self):
        from movies_app.tasks.colombia_com_download_task import (
            _extract_showtimes_from_html,
        )

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "colombia_dot_com___vizcay_cine_colombia.html",
        )

        with open(html_snapshot_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        movie_showtimes = _extract_showtimes_from_html(html_content)

        for ms in movie_showtimes:
            assert ms.movie_url is not None, f"Movie '{ms.movie_name}' should have a URL"
            assert ms.movie_url.startswith("https://www.colombia.com/cine/"), (
                f"Movie URL should start with colombia.com: {ms.movie_url}"
            )


class TestExtractMovieMetadata:
    def test_extracts_metadata_from_movie_page_html(self):
        from movies_app.tasks.colombia_com_download_task import (
            _extract_movie_metadata_from_html,
        )

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "colombia_dot_com___individual_movie.html",
        )

        with open(html_snapshot_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        metadata = _extract_movie_metadata_from_html(html_content)

        assert metadata is not None
        assert metadata.genre == "Terror"
        assert metadata.duration_minutes == 85
        assert metadata.classification == "18 Años"
        assert metadata.director == "Sasha Sibley"
        assert "Aleksa Palladino" in metadata.actors
        assert "Jadon Cal" in metadata.actors
        assert "Sean Bridgers" in metadata.actors
        assert "Ene 15 / 2026" in metadata.release_date

    def test_parse_release_year_from_colombia_date(self):
        from movies_app.tasks.colombia_com_download_task import (
            _parse_release_year_from_colombia_date,
        )

        assert _parse_release_year_from_colombia_date("Ene 15 / 2026") == 2026
        assert _parse_release_year_from_colombia_date("Dic 25 / 2025") == 2025
        assert _parse_release_year_from_colombia_date("") is None
        assert _parse_release_year_from_colombia_date("Invalid") is None
