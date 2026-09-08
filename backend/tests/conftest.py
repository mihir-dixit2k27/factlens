"""Pytest configuration and shared fixtures."""
from __future__ import annotations
import pytest


@pytest.fixture(autouse=True)
def set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Set test environment variables."""
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    monkeypatch.setenv("DATABASE_URL", "postgresql://factlens:factlens@localhost:5432/factlens_test")
    monkeypatch.setenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")
