"""
Load theaters from seed_data/theaters.json into the database.

Usage:
    # Load all theaters from all cities
    python manage.py load_theaters --all-theaters

    # Load theaters from specific city/cities
    python manage.py load_theaters --city Medellín
    python manage.py load_theaters --city Medellín --city Envigado

    # List available cities without loading
    python manage.py load_theaters --list-cities

This command performs an upsert operation using the theater's slug as the
unique identifier. If a theater with the same slug exists, it will be updated.
Otherwise, a new theater will be created.

The seed data file is located at: seed_data/theaters.json
The file is organized by city, with each city containing an array of theaters.
"""

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from movies_app.models import Theater


class Command(BaseCommand):
    help = "Load theaters from seed_data/theaters.json (upsert by slug)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--city",
            action="append",
            dest="cities",
            help="Load theaters only from specified city (can be used multiple times)",
        )
        parser.add_argument(
            "--list-cities",
            action="store_true",
            help="List available cities and theater counts without loading",
        )
        parser.add_argument(
            "--all-theaters",
            action="store_true",
            help="Load theaters from all cities",
        )

    def handle(self, *args, **options):
        seed_file = Path(__file__).resolve().parent.parent.parent.parent / "seed_data" / "theaters.json"

        if not seed_file.exists():
            self.stderr.write(self.style.ERROR(f"Seed file not found: {seed_file}"))
            return

        with open(seed_file) as f:
            theaters_by_city = json.load(f)

        if options["list_cities"]:
            self._list_cities(theaters_by_city)
            return

        cities_to_load = options["cities"]
        load_all = options["all_theaters"]

        if not cities_to_load and not load_all:
            self.stderr.write(
                self.style.ERROR("Must specify --city or --all-theaters")
            )
            return

        if cities_to_load and load_all:
            self.stderr.write(
                self.style.ERROR("Cannot use both --city and --all-theaters")
            )
            return

        if load_all:
            cities_to_load = list(theaters_by_city.keys())
        else:
            # Validate requested cities exist
            invalid_cities = set(cities_to_load) - set(theaters_by_city.keys())
            if invalid_cities:
                self.stderr.write(
                    self.style.ERROR(f"Unknown cities: {', '.join(invalid_cities)}")
                )
                self.stderr.write(f"Available cities: {', '.join(theaters_by_city.keys())}")
                return

        created_count = 0
        updated_count = 0
        unchanged_count = 0

        for city in cities_to_load:
            theaters_data = theaters_by_city[city]
            self.stdout.write(f"\n{city} ({len(theaters_data)} theaters):")

            for data in theaters_data:
                slug = data["slug"]
                new_values = {
                    "name": data["name"],
                    "chain": data.get("chain", ""),
                    "address": data["address"],
                    "city": city,
                    "neighborhood": data.get("neighborhood", ""),
                    "phone": data.get("phone", ""),
                    "screen_count": data.get("screen_count"),
                    "website": data.get("website", ""),
                    "colombia_dot_com_url": data.get("colombia_dot_com_url", ""),
                }

                theater = Theater.objects.filter(slug=slug).first()

                if theater is None:
                    Theater.objects.create(slug=slug, **new_values)
                    created_count += 1
                    self.stdout.write(f"  Created: {new_values['name']}")
                else:
                    changed_fields = self._get_changed_fields(theater, new_values)
                    if changed_fields:
                        for field, value in new_values.items():
                            setattr(theater, field, value)
                        theater.save()
                        updated_count += 1
                        self.stdout.write(f"  Updated: {theater.name} ({', '.join(changed_fields)})")
                    else:
                        unchanged_count += 1
                        self.stdout.write(f"  Unchanged: {theater.name}")

        self.stdout.write(
            self.style.SUCCESS(
                f"\nDone. Created: {created_count}, Updated: {updated_count}, Unchanged: {unchanged_count}"
            )
        )

    def _list_cities(self, theaters_by_city: dict):
        """List all available cities and their theater counts."""
        self.stdout.write("\nAvailable cities:")
        total = 0
        for city, theaters in theaters_by_city.items():
            count = len(theaters)
            total += count
            self.stdout.write(f"  {city}: {count} theaters")
        self.stdout.write(self.style.SUCCESS(f"\nTotal: {total} theaters"))

    def _get_changed_fields(self, theater: Theater, new_values: dict) -> list[str]:
        """Return list of field names that differ between theater and new_values."""
        changed = []
        for field, new_value in new_values.items():
            current_value = getattr(theater, field)
            if current_value != new_value:
                changed.append(field)
        return changed
