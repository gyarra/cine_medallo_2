"""
Download From Colombia.com Task

Celery task for scraping movie showtime data from colombia.com.
"""

import logging

from config.celery_app import app

logger = logging.getLogger(__name__)


@app.task
def download_from_colombia_dot_com_task():
    """
    Celery task to download movie showtime data from colombia.com.

    Scheduled to run every 10 minutes.
    """
    logger.info("Starting download_from_colombia_dot_com_task")
