"""
Load theaters from seed_data/theaters.json into the database.

Usage:
    python manage.py load_theaters

This command performs an upsert operation using the theater's slug as the
unique identifier. If a theater with the same slug exists, it will be updated.
Otherwise, a new theater will be created.

The seed data file is located at: seed_data/theaters.json
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from movies_app.models import Theater


class Command(BaseCommand):
    help = "Load theaters from seed_data/theaters.json (upsert by slug)"

    def handle(self, *args, **options):
        seed_file = Path(__file__).resolve().parent.parent.parent.parent / "seed_data" / "theaters.json"

        if not seed_file.exists():
            self.stderr.write(self.style.ERROR(f"Seed file not found: {seed_file}"))
            return

        with open(seed_file) as f:
            theaters_data = json.load(f)

        created_count = 0
        updated_count = 0

        for data in theaters_data:
            slug = data["slug"]
            defaults = {
                "name": data["name"],
                "chain": data.get("chain", ""),
                "address": data["address"],
                "city": data["city"],
                "neighborhood": data.get("neighborhood", ""),
                "phone": data.get("phone", ""),
                "screen_count": data.get("screen_count"),
                "website": data.get("website", ""),
            }

            theater, created = Theater.objects.update_or_create(
                slug=slug,
                defaults=defaults,
            )

            if created:
                created_count += 1
                self.stdout.write(f"  Created: {theater.name}")
            else:
                updated_count += 1
                self.stdout.write(f"  Updated: {theater.name}")

        self.stdout.write(
            self.style.SUCCESS(f"\nDone. Created: {created_count}, Updated: {updated_count}")
        )
