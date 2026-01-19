"""
Django management command to execute the download_from_colombia_dot_com task.
"""

from django.core.management.base import BaseCommand

from movies_app.tasks.download_from_colombia_dot_com import download_from_colombia_dot_com_task


class Command(BaseCommand):
    help = "Download movie showtime data from colombia.com"

    def handle(self, *args, **options):
        self.stdout.write("Executing download_from_colombia_dot_com_task...")
        download_from_colombia_dot_com_task()
        self.stdout.write(self.style.SUCCESS("Task completed."))
