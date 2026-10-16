"""Pytest configuration and shared fixtures for s2motion tests."""

import pytest


def pytest_configure(config: pytest.Config) -> None:
    """Register custom markers."""
    config.addinivalue_line(
        "markers",
        "network: mark test as requiring internet access to remote STAC endpoints",
    )
