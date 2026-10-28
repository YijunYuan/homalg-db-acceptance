"""Isolated, small checkouts for tests that exercise file generation."""

from pathlib import Path

import pytest
from fixture_support import copy_baseline_repository

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    """Copy only authored fixtures and contracts, never the Mathlib cache."""
    return copy_baseline_repository(ROOT, tmp_path)
