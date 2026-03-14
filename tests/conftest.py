from __future__ import annotations

from pathlib import Path

import pytest

from onboardai.config import detect_dataset_root


@pytest.fixture()
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture()
def dataset_root(project_root: Path) -> Path:
    return detect_dataset_root(project_root)
