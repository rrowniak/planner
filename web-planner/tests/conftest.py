from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = ROOT.parent
EXAMPLES_DIR = REPO_ROOT / "examples"
CALENDAR_FILE = ROOT / "calendars" / "calendar_pl.toml"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def calendar_toml() -> str:
    return CALENDAR_FILE.read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def simple_project_toml() -> str:
    return (EXAMPLES_DIR / "simple_project.toml").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def complex_project_toml() -> str:
    return (EXAMPLES_DIR / "complex_project.toml").read_text(encoding="utf-8")


@pytest.fixture(scope="session")
def calendar_file_name() -> str:
    return "calendar_pl.toml"
