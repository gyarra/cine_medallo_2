"""
Celery configuration for cine_medallo_2 application.

This module configures Celery for handling background tasks including
web scraping for movie showtimes.
"""

import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('config')

app.config_from_object('django.conf:settings', namespace='CELERY')

app.autodiscover_tasks()
app.autodiscover_tasks(['movies_app.tasks'])

app.conf.update(
    broker_url=os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    result_backend=os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0'),
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='America/Bogota',
    enable_utc=False,
    task_always_eager=False,
    task_eager_propagates=True,
    task_ignore_result=False,
    task_store_eager_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=60,
    task_max_retries=1,
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=1000,
    task_queues={
        'celery': {},
        'scraping': {},
    },
    task_default_queue='celery',
    task_routes={
        'movies_app.tasks.download_from_colombia_dot_com.*': {'queue': 'scraping'},
    },
    result_expires=3600,
    beat_schedule={
        'download-from-colombia-dot-com': {
            'task': 'movies_app.tasks.download_from_colombia_dot_com.download_from_colombia_dot_com_task',
            'schedule': 600.0,  # Every 10 minutes (600 seconds)
        },
    },
)
