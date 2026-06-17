from datetime import datetime

import icalendar
import pytest

from ics_caldav_sync import ICSToCalDAV


def make_event(**props) -> icalendar.Event:
    event = icalendar.Event()
    for k, v in props.items():
        event.add(k, v)
    return event


@pytest.fixture()
def comparator():
    """A minimal ICSToCalDAV-like object with just the _compare method and ignored_compare_fields."""
    obj = object.__new__(ICSToCalDAV)
    obj.ignored_compare_fields = []
    return obj


class TestCompareIdentical:
    def test_identical_events(self, comparator):
        a = make_event(summary="Meeting", dtstart=datetime(2025, 1, 1, 12))
        b = make_event(summary="Meeting", dtstart=datetime(2025, 1, 1, 12))
        assert comparator._compare(a, b)

    def test_empty_events(self, comparator):
        assert comparator._compare(icalendar.Event(), icalendar.Event())


class TestCompareDifferent:
    def test_different_summary(self, comparator):
        a = make_event(summary="Meeting", dtstart=datetime(2025, 1, 1, 12))
        b = make_event(summary="Lunch", dtstart=datetime(2025, 1, 1, 12))
        assert not comparator._compare(a, b)

    def test_different_start(self, comparator):
        a = make_event(summary="Meeting", dtstart=datetime(2025, 1, 1, 12))
        b = make_event(summary="Meeting", dtstart=datetime(2025, 1, 1, 14))
        assert not comparator._compare(a, b)

    def test_extra_field(self, comparator):
        a = make_event(summary="Meeting", dtstart=datetime(2025, 1, 1, 12))
        b = make_event(summary="Meeting", dtstart=datetime(2025, 1, 1, 12), location="Room 1")
        assert not comparator._compare(a, b)


class TestCompareIgnoredFields:
    def test_ignored_field_makes_different_events_equal(self, comparator):
        comparator.ignored_compare_fields = ["DTSTAMP"]
        a = make_event(summary="Meeting", dtstamp=datetime(2025, 1, 1, 10))
        b = make_event(summary="Meeting", dtstamp=datetime(2025, 6, 1, 10))
        assert comparator._compare(a, b)

    def test_ignored_field_missing_from_one_event(self, comparator):
        comparator.ignored_compare_fields = ["DTSTAMP"]
        a = make_event(summary="Meeting", dtstamp=datetime(2025, 1, 1, 10))
        b = make_event(summary="Meeting")
        assert comparator._compare(a, b)

    def test_multiple_ignored_fields(self, comparator):
        comparator.ignored_compare_fields = ["DTSTAMP", "SEQUENCE"]
        a = make_event(summary="Meeting", dtstamp=datetime(2025, 1, 1), sequence=1)
        b = make_event(summary="Meeting", dtstamp=datetime(2025, 6, 1), sequence=5)
        assert comparator._compare(a, b)

    def test_still_differs_on_non_ignored_field(self, comparator):
        comparator.ignored_compare_fields = ["DTSTAMP"]
        a = make_event(summary="Meeting", dtstamp=datetime(2025, 1, 1))
        b = make_event(summary="Lunch", dtstamp=datetime(2025, 1, 1))
        assert not comparator._compare(a, b)


class TestCompareDoesNotMutate:
    def test_originals_unchanged(self, comparator):
        comparator.ignored_compare_fields = ["DTSTAMP"]
        a = make_event(summary="Meeting", dtstamp=datetime(2025, 1, 1))
        b = make_event(summary="Meeting", dtstamp=datetime(2025, 6, 1))
        comparator._compare(a, b)
        assert "DTSTAMP" in a
        assert "DTSTAMP" in b
