"""Pytest conftest for evaluation tests — adds helpers to sys.path."""

import sys
from pathlib import Path

# Make helpers importable
sys.path.insert(0, str(Path(__file__).parent))
