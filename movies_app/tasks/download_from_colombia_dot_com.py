"""
Download From Colombia.com Task

Celery task for scraping movie showtime data from colombia.com.
"""

import logging

from bs4 import BeautifulSoup

from config.celery_app import app

logger = logging.getLogger(__name__)


def _extract_movie_names_from_html(html_content: str) -> list[str]:
    """
    Extract movie names from colombia.com theater page HTML.

    Args:
        html_content: Raw HTML content from a colombia.com theater page.

    Returns:
        List of movie names found in the HTML.
    """
    soup = BeautifulSoup(html_content, "lxml")
    movie_divs = soup.find_all("div", class_="nombre-pelicula")

    movie_names = []
    for div in movie_divs:
        anchor = div.find("a")
        if anchor and anchor.string:
            movie_names.append(anchor.string.strip())

    return movie_names


@app.task
def download_from_colombia_dot_com_task():
    """
    Celery task to download movie showtime data from colombia.com.

    Scheduled to run every 10 minutes.
    """
    logger.info("Starting download_from_colombia_dot_com_task")
