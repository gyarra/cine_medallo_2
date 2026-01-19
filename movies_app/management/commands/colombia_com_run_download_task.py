"""
Django management command to execute the colombia_com_download_task.
"""

from django.core.management.base import BaseCommand

from movies_app.tasks.colombia_com_download_task import colombia_com_download_task


class Command(BaseCommand):
    help = "Download movie showtime data from colombia.com"

    def handle(self, *args, **options):
        self.stdout.write("Executing colombia_com_download_task...")
        colombia_com_download_task()
        self.stdout.write(self.style.SUCCESS("Task completed."))
