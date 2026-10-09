"""Scenario tests drive the API like the browser does, so they share the API fixtures."""

from tests.api.conftest import make_api

__all__ = ["make_api"]
