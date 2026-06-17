from datetime import datetime
from unittest.mock import MagicMock, PropertyMock

import caldav.lib.error
import icalendar
import pytest

from ics_caldav_sync import ICSToCalDAV


def make_event(**props) -> icalendar.Event:
    event = icalendar.Event()
    for k, v in props.items():
        event.add(k, v)
    return event


@pytest.fixture()
def syncer():
    obj = object.__new__(ICSToCalDAV)
    obj.ignored_compare_fields = []
    obj.sync_all = True
    obj.keep_local = True
    obj.local_calendar = MagicMock()
    obj.local_client = MagicMock()
    obj.remote_calendar = MagicMock()
    return obj


class TestSynchroniseUsesCompare:
    def test_skips_identical_event(self, syncer):
        event = make_event(summary="Meeting", uid="123", dtstamp=datetime(2025, 1, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[event])
        syncer.local_calendar.get_event_by_uid.return_value.icalendar_component = event

        syncer.synchronise()

        syncer.local_calendar.save_event.assert_not_called()

    def test_saves_new_event(self, syncer):
        event = make_event(summary="Meeting", uid="123", dtstamp=datetime(2025, 1, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[event])
        syncer.local_calendar.get_event_by_uid.side_effect = caldav.lib.error.NotFoundError

        syncer.synchronise()

        syncer.local_calendar.save_event.assert_called_once()

    def test_saves_changed_event(self, syncer):
        remote = make_event(summary="Updated", uid="123", dtstamp=datetime(2025, 1, 1))
        local = make_event(summary="Original", uid="123", dtstamp=datetime(2025, 1, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[remote])
        syncer.local_calendar.get_event_by_uid.return_value.icalendar_component = local

        syncer.synchronise()

        syncer.local_calendar.save_event.assert_called_once()

    def test_skips_with_ignored_fields(self, syncer):
        """Events that differ only in ignored fields should be skipped."""
        syncer.ignored_compare_fields = ["DTSTAMP"]
        a = make_event(summary="Meeting", uid="123", dtstamp=datetime(2025, 1, 1))
        b = make_event(summary="Meeting", uid="123", dtstamp=datetime(2025, 6, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[a])
        syncer.local_calendar.get_event_by_uid.return_value.icalendar_component = b

        syncer.synchronise()

        syncer.local_calendar.save_event.assert_not_called()

    def test_saves_when_ignored_fields_not_only_difference(self, syncer):
        """Events that differ on non-ignored fields should still be saved."""
        syncer.ignored_compare_fields = ["DTSTAMP"]
        remote = make_event(summary="Updated", uid="123", dtstamp=datetime(2025, 1, 1))
        local = make_event(summary="Original", uid="123", dtstamp=datetime(2025, 6, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[remote])
        syncer.local_calendar.get_event_by_uid.return_value.icalendar_component = local

        syncer.synchronise()

        syncer.local_calendar.save_event.assert_called_once()
