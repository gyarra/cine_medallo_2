#!/bin/bash

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
fi

# Sync dependencies (creates .venv if needed)
uv sync --extra dev  # Use --all-extras on macOS for pyobjc support

# Activate virtual environment for subsequent commands
source .venv/bin/activate

# Install Camoufox browser
python -m camoufox fetch

# Check for .env file
if [ ! -f .env ]; then
    echo ""
    echo "WARNING: No .env file found. Create one with:"
    echo "  DATABASE_URL=postgres://..."
    echo "  TMDB_READ_ACCESS_TOKEN=..."
    echo "  SUPABASE_IMAGES_BUCKET_URL=..."
    echo "  SUPABASE_IMAGES_BUCKET_ACCESS_KEY_ID=..."
    echo "  SUPABASE_IMAGES_BUCKET_SECRET_ACCESS_KEY=..."
    echo "  SUPABASE_IMAGES_BUCKET_NAME=..."
    echo ""
fi

# Run Django checks
python manage.py check

# Run migrations
python manage.py migrate

# Load theater seed data
python manage.py load_theaters

echo ""
echo "Setup complete! Run 'source .venv/bin/activate' to activate the virtual environment."
