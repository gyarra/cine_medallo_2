"""
Background Tasks

Powered by Celery for distributed task execution.
"""

from . import download_from_colombia_dot_com

__all__ = [
    'download_from_colombia_dot_com',
]
