"""
Background Tasks

Powered by Celery for distributed task execution.
"""

from . import colombia_com_download_task

__all__ = [
    'colombia_com_download_task',
]
