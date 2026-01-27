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

# Run Django checks
python manage.py check
