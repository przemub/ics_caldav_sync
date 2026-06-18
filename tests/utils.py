"""Shared test helpers."""
import pathlib

import icalendar

FIXTURES = pathlib.Path(__file__).parent / "fixtures"


def read_fixture(name) -> str:
    """Return a fixture's text with CRLF line endings, as required by RFC 5545."""
    return (FIXTURES / name).read_text().replace("\n", "\r\n")


def load_fixture(name) -> icalendar.Calendar:
    """Parse a fixture into an icalendar.Calendar."""
    return icalendar.Calendar.from_ical(read_fixture(name))
