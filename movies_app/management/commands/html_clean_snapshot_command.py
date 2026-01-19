"""
Django management command for cleaning HTML snapshot files.

Usage:
    python manage.py html_clean_snapshot_command <html_file_path>
    python manage.py html_clean_snapshot_command /path/to/file.html --dry-run
"""
import os
from pathlib import Path
from bs4 import BeautifulSoup
import re
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Clean HTML snapshot files by removing scripts, styles, and unnecessary elements'

    def add_arguments(self, parser):
        parser.add_argument(
            'html_file',
            type=str,
            help='Path to the HTML file to clean'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be cleaned without making changes'
        )

    def handle(self, *args, **options):
        self._clean_single_file(options['html_file'], dry_run=options.get('dry_run', False))

    def _clean_single_file(self, file_path, dry_run):
        """Clean a single HTML file."""
        if not os.path.isabs(file_path):
            base_dir = Path(__file__).resolve().parent.parent.parent.parent
            possible_paths = [
                base_dir / file_path,
                base_dir / 'movies_app' / 'tasks' / 'tests' / 'html_snapshot' / file_path,
            ]

            for path in possible_paths:
                if path.exists():
                    file_path = str(path)
                    break
            else:
                raise CommandError(f'File not found: {file_path}')

        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN - Would clean: {file_path}'))
            return

        try:
            self._clean_html_file(file_path)
            links_count = self._validate_article_links(file_path)

            if links_count > 0:
                self.stdout.write(self.style.SUCCESS('✅ Cleaning completed successfully!'))
            else:
                self.stdout.write(
                    self.style.WARNING('⚠️  Warning: No article links found after cleaning. Please verify the file.')
                )

        except Exception as e:
            raise CommandError(f'Error cleaning file: {e}')

    def _clean_html_file(self, file_path):
        """
        Clean an HTML file by removing scripts, styles, and unnecessary elements.

        Args:
            file_path (str): Path to the HTML file to clean

        Returns:
            tuple: (original_size, cleaned_size, reduction_percentage)
        """
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")

        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        original_size = len(html_content)

        soup = BeautifulSoup(html_content, 'html.parser')

        scripts_removed = len(soup.find_all("script"))
        for script in soup.find_all("script"):
            script.decompose()

        styles_removed = len(soup.find_all("style"))
        for style in soup.find_all("style"):
            style.decompose()

        inline_styles_removed = 0
        for tag in soup.find_all(True):
            if tag.has_attr('style'):
                del tag['style']
                inline_styles_removed += 1

        event_handlers_removed = 0
        for tag in soup.find_all(True):
            attrs_to_remove = []
            for attr in tag.attrs:
                if attr.startswith('on'):
                    attrs_to_remove.append(attr)
            for attr in attrs_to_remove:
                del tag[attr]
                event_handlers_removed += 1

        empty_elements_removed = 0
        for tag in soup.find_all(['div', 'span']):
            if not tag.get_text(strip=True) and not tag.find_all():
                tag.decompose()
                empty_elements_removed += 1

        cleaned_html = str(soup)
        cleaned_size = len(cleaned_html)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(cleaned_html)

        reduction_percentage = (1 - cleaned_size/original_size) * 100

        self.stdout.write(f"✅ Successfully cleaned HTML file: {file_path}")
        self.stdout.write(
            f"📊 Statistics:"
            f"\n   - Scripts removed: {scripts_removed}"
            f"\n   - Style blocks removed: {styles_removed}"
            f"\n   - Inline styles removed: {inline_styles_removed}"
            f"\n   - Event handlers removed: {event_handlers_removed}"
            f"\n   - Empty elements removed: {empty_elements_removed}"
            f"\n   - Original size: {original_size:,} characters"
            f"\n   - Cleaned size: {cleaned_size:,} characters"
            f"\n   - Size reduction: {reduction_percentage:.1f}%"
        )

        return original_size, cleaned_size, reduction_percentage

    def _validate_article_links(self, file_path, expected_pattern=r'^/[^/]+/[^/]+-[A-Z]{2}\d+'):
        """
        Validate that article links are still present after cleaning.

        Args:
            file_path (str): Path to the cleaned HTML file
            expected_pattern (str): Regex pattern for article links

        Returns:
            int: Number of article links found
        """
        with open(file_path, "r", encoding="utf-8") as f:
            html_content = f.read()

        soup = BeautifulSoup(html_content, 'html.parser')
        links = set()

        for link in soup.find_all('a', href=True):
            href = str(link['href'])
            if re.match(expected_pattern, href):
                links.add(href)

        self.stdout.write(
            f"🔗 Article links validation:"
            f"\n   - Links found: {len(links)}"
        )
        if len(links) > 0:
            self.stdout.write(f"   - Sample links: {list(links)[:3]}")

        return len(links)
