"""Basic sanity test for package import and version."""

import s2motion


def test_version() -> None:
    """Verify package version is set."""
    assert s2motion.__version__ == "0.1.0"
