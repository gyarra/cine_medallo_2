#!/bin/bash
source .venv/bin/activate
pytest -s -v --log-level=INFO --cov --cov-report=
