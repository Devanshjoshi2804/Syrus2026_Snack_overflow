from __future__ import annotations

from pathlib import Path

import pytest

from onboardai.config import detect_dataset_root


@pytest.fixture(autouse=True)
def stable_test_env(monkeypatch):
    monkeypatch.setenv("ONBOARDAI_SANDBOX_BACKEND", "mock")
    monkeypatch.setenv("ONBOARDAI_BROWSER_BACKEND", "mock")
    monkeypatch.setenv("ONBOARDAI_BROWSER_HEADLESS", "true")


@pytest.fixture()
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture()
def dataset_root(project_root: Path) -> Path:
    return detect_dataset_root(project_root)
