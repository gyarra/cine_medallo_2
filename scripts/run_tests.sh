#!/bin/bash
source .venv/bin/activate
pytest -s -v --log-level=DEBUG --cov --cov-report=term-missing --cov-report=html
