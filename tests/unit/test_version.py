"""Basic package smoke test."""

from ravi import __version__


def test_version():
    assert __version__ == "0.1.0"
