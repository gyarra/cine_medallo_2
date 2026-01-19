import os

import pytest


@pytest.mark.django_db
class TestExtractMovieNamesFromHtml:
    def test_extracts_movie_names_from_colombia_dot_com_html(self):
        from movies_app.tasks.colombia_com_download_task import (
            _extract_movie_names_from_html,
        )

        html_snapshot_path = os.path.join(
            os.path.dirname(__file__),
            "html_snapshot",
            "colombia_dot_com___vizcay_cine_colombia.html",
        )

        with open(html_snapshot_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        movie_names = _extract_movie_names_from_html(html_content)

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
