"""Unit-test the synchronise method."""
from datetime import date, datetime, timezone, timedelta
from unittest.mock import MagicMock, PropertyMock

import caldav.lib.error
import icalendar
import pytest
import vobject.base

from ics_caldav_sync import ICSToCalDAV


def make_event(**props) -> icalendar.Event:
    event = icalendar.Event()
    for k, v in props.items():
        event.add(k, v)
    return event


def stored_instance(*events) -> icalendar.Calendar:
    """Build the VCALENDAR that get_event_by_uid(...).icalendar_instance would
    return for an event already stored on the server."""
    calendar = icalendar.Calendar()
    for event in events:
        calendar.add_component(event)
    return calendar


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
        remote = make_event(summary="Meeting", uid="123", dtstamp=datetime(2025, 1, 1))
        local = make_event(summary="Meeting", uid="123", dtstamp=datetime(2025, 1, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[remote])
        syncer.local_calendar.get_event_by_uid.return_value.icalendar_instance = (
            stored_instance(local)
        )

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
        syncer.local_calendar.get_event_by_uid.return_value.icalendar_instance = (
            stored_instance(local)
        )

        syncer.synchronise()

        syncer.local_calendar.save_event.assert_called_once()

    def test_skips_with_ignored_fields(self, syncer):
        """Events that differ only in ignored fields should be skipped."""
        syncer.ignored_compare_fields = ["DTSTAMP"]
        a = make_event(summary="Meeting", uid="123", dtstamp=datetime(2025, 1, 1))
        b = make_event(summary="Meeting", uid="123", dtstamp=datetime(2025, 6, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[a])
        syncer.local_calendar.get_event_by_uid.return_value.icalendar_instance = (
            stored_instance(b)
        )

        syncer.synchronise()

        syncer.local_calendar.save_event.assert_not_called()

    def test_saves_when_ignored_fields_not_only_difference(self, syncer):
        """Events that differ on non-ignored fields should still be saved."""
        syncer.ignored_compare_fields = ["DTSTAMP"]
        remote = make_event(summary="Updated", uid="123", dtstamp=datetime(2025, 1, 1))
        local = make_event(summary="Original", uid="123", dtstamp=datetime(2025, 6, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[remote])
        syncer.local_calendar.get_event_by_uid.return_value.icalendar_instance = (
            stored_instance(local)
        )

        syncer.synchronise()

        syncer.local_calendar.save_event.assert_called_once()


class TestSynchroniseGroupsRecurrence:
    def test_parent_and_override_saved_to_one_resource(self, syncer):
        """A recurrence override (RECURRENCE-ID) shares its parent's UID, so the
        two must be written to a single resource (one save) rather than saved
        separately, where each would overwrite the other at <uid>.ics."""
        parent = make_event(summary="Parent", uid="123", dtstamp=datetime(2025, 1, 1))
        override = make_event(summary="Override", uid="123", dtstamp=datetime(2025, 1, 1))
        override.add("RECURRENCE-ID", datetime(2025, 1, 2))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[override, parent])
        syncer.local_calendar.get_event_by_uid.side_effect = caldav.lib.error.NotFoundError

        syncer.synchronise()

        syncer.local_calendar.save_event.assert_called_once()
        payload = syncer.local_calendar.save_event.call_args.args[0]
        # Both events live in the one VCALENDAR (order is irrelevant per RFC 5545).
        assert payload.count(b"BEGIN:VEVENT") == 2
        assert b"SUMMARY:Parent" in payload
        assert b"SUMMARY:Override" in payload


class TestIsPast:
    """_is_past picks the right "now" for date / naive- / aware-datetime ends.

    A fixed reference time is injected so the boundaries are exact and the
    result never depends on the wall clock.
    """

    NOW_NAIVE = datetime(2025, 6, 1, 12, 0, 0)
    NOW_AWARE = datetime(2025, 6, 1, 12, 0, 0, tzinfo=timezone.utc)
    TODAY = date(2025, 6, 1)

    def is_past(self, event):
        obj = object.__new__(ICSToCalDAV)
        obj._now_naive = self.NOW_NAIVE
        obj._now_aware = self.NOW_AWARE
        obj._today = self.TODAY
        return obj._is_past(event)

    # All-day events compare end (a date) against today with `today > end`.
    def test_date_before_today_is_past(self):
        assert self.is_past(
            make_event(dtstart=date(2025, 5, 30), dtend=date(2025, 5, 31))
        )

    def test_date_equal_today_is_not_past(self):
        # Boundary: ending exactly today is NOT past.
        assert not self.is_past(make_event(dtstart=self.TODAY, dtend=self.TODAY))

    def test_date_after_today_is_not_past(self):
        assert not self.is_past(
            make_event(dtstart=date(2025, 6, 2), dtend=date(2025, 6, 3))
        )

    # Naive datetimes compare against now_naive.
    def test_naive_before_now_is_past(self):
        assert self.is_past(
            make_event(
                dtstart=datetime(2025, 6, 1, 10), dtend=datetime(2025, 6, 1, 11)
            )
        )

    def test_naive_after_now_is_not_past(self):
        assert not self.is_past(
            make_event(
                dtstart=datetime(2025, 6, 1, 13), dtend=datetime(2025, 6, 1, 14)
            )
        )

    # Aware datetimes compare against now_aware.
    def test_aware_before_now_is_past(self):
        assert self.is_past(
            make_event(
                dtstart=datetime(2025, 6, 1, 10, tzinfo=timezone.utc),
                dtend=datetime(2025, 6, 1, 11, tzinfo=timezone.utc),
            )
        )

    def test_aware_after_now_is_not_past(self):
        assert not self.is_past(
            make_event(
                dtstart=datetime(2025, 6, 1, 13, tzinfo=timezone.utc),
                dtend=datetime(2025, 6, 1, 14, tzinfo=timezone.utc),
            )
        )


class TestSynchronisePastEventFiltering:
    """synchronise() applies _is_past per UID group when sync_all is off."""

    _past = date.today() - timedelta(days=365)
    _future = date.today() + timedelta(days=365)

    def _run(self, syncer, *events):
        syncer.sync_all = False
        type(syncer.remote_calendar).events = PropertyMock(return_value=list(events))
        syncer.local_calendar.get_event_by_uid.side_effect = (
            caldav.lib.error.NotFoundError
        )
        syncer.synchronise()

    def test_past_event_is_skipped(self, syncer):
        self._run(
            syncer, make_event(uid="1", dtstart=self._past, dtend=self._past + timedelta(days=1))
        )
        syncer.local_calendar.save_event.assert_not_called()

    def test_future_event_is_saved(self, syncer):
        self._run(
            syncer, make_event(uid="1", dtstart=self._future, dtend=self._future + timedelta(days=1))
        )
        syncer.local_calendar.save_event.assert_called_once()

    def test_group_kept_when_any_event_is_future(self, syncer):
        """A past parent with a future override (same UID) must be kept whole."""
        parent = make_event(uid="1", dtstart=self._past, dtend=self._past + timedelta(days=1))
        override = make_event(uid="1", dtstart=self._future, dtend=self._future + timedelta(days=1))
        override.add("RECURRENCE-ID", self._future)
        self._run(syncer, parent, override)
        syncer.local_calendar.save_event.assert_called_once()

    def test_group_skipped_when_all_events_past(self, syncer):
        parent = make_event(uid="1", dtstart=self._past, dtend=self._past + timedelta(days=1))
        override = make_event(uid="1", dtstart=self._past + timedelta(days=180), dtend=self._past + timedelta(days=181))
        override.add("RECURRENCE-ID", self._past + timedelta(days=180))
        self._run(syncer, parent, override)
        syncer.local_calendar.save_event.assert_not_called()


class TestSynchroniseDeleteBranch:
    """When keep_local is off, local events absent from the remote are deleted."""

    def test_deletes_stale_local_event(self, syncer):
        syncer.keep_local = False
        remote = make_event(summary="Kept", uid="A", dtstamp=datetime(2025, 1, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[remote])
        syncer.local_calendar.get_event_by_uid.side_effect = (
            caldav.lib.error.NotFoundError
        )
        # Local has A (in remote) and B (stale) -> only B should be deleted.
        syncer._get_local_events_ids = MagicMock(return_value={"A", "B"})

        syncer.synchronise()

        # Only the stale event (B) is deleted; the one still in the remote (A)
        # is left alone.
        syncer.local_client.delete.assert_called_once()
        deleted_url = syncer.local_client.delete.call_args.args[0]
        assert "B.ics" in deleted_url
        assert "A.ics" not in deleted_url

    def test_no_deletion_when_nothing_stale(self, syncer):
        syncer.keep_local = False
        remote = make_event(summary="Kept", uid="A", dtstamp=datetime(2025, 1, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[remote])
        syncer.local_calendar.get_event_by_uid.side_effect = (
            caldav.lib.error.NotFoundError
        )
        syncer._get_local_events_ids = MagicMock(return_value={"A"})

        syncer.synchronise()

        syncer.local_client.delete.assert_not_called()


class TestSynchroniseUidlessEvent:
    def test_event_without_uid_is_skipped_not_fatal(self, syncer):
        """RFC 5545 requires a UID, but some exporters omit it. Such an event
        cannot be addressed on the CalDAV server, so it is skipped with a
        warning; the other events still sync and deletion is unaffected."""
        uidless = make_event(summary="NoUid", dtstamp=datetime(2025, 1, 1))
        good = make_event(summary="Good", uid="A", dtstamp=datetime(2025, 1, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[uidless, good])
        syncer.local_calendar.get_event_by_uid.side_effect = (
            caldav.lib.error.NotFoundError
        )
        syncer.keep_local = False
        syncer._get_local_events_ids = MagicMock(return_value={"A"})

        syncer.synchronise()

        syncer.local_calendar.save_event.assert_called_once()
        payload = syncer.local_calendar.save_event.call_args.args[0]
        assert b"SUMMARY:Good" in payload
        assert b"SUMMARY:NoUid" not in payload
        syncer.local_client.delete.assert_not_called()


class TestSynchroniseValidateError:
    def test_invalid_event_is_skipped_not_fatal(self, syncer):
        """A vobject ValidateError on save is logged and skipped; later events
        are still processed."""
        a = make_event(summary="Bad", uid="A", dtstamp=datetime(2025, 1, 1))
        b = make_event(summary="AlsoBad", uid="B", dtstamp=datetime(2025, 1, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[a, b])
        syncer.local_calendar.get_event_by_uid.side_effect = (
            caldav.lib.error.NotFoundError
        )
        syncer.local_calendar.save_event.side_effect = vobject.base.ValidateError(
            "invalid"
        )

        # Should not raise, and both events should have been attempted.
        syncer.synchronise()

        assert syncer.local_calendar.save_event.call_count == 2


class TestSynchroniseHandlesPutError:
    def test_skips_event_with_no_recurrence_instances(self, syncer):
        """A sabre/dav NoInstancesException is logged and skipped, not fatal."""
        event = make_event(summary="Empty rule", uid="123", dtstamp=datetime(2025, 1, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[event])
        syncer.local_calendar.get_event_by_uid.side_effect = caldav.lib.error.NotFoundError
        syncer.local_calendar.save_event.side_effect = caldav.lib.error.PutError(
            "400 Bad Request\n\n<s:exception>Sabre\\VObject\\Recur\\NoInstancesException</s:exception>"
        )

        # Should not raise.
        syncer.synchronise()

        syncer.local_calendar.save_event.assert_called_once()

    def test_other_put_errors_propagate(self, syncer):
        """A PutError that is not a NoInstancesException must still be fatal."""
        event = make_event(summary="Meeting", uid="123", dtstamp=datetime(2025, 1, 1))
        type(syncer.remote_calendar).events = PropertyMock(return_value=[event])
        syncer.local_calendar.get_event_by_uid.side_effect = caldav.lib.error.NotFoundError
        syncer.local_calendar.save_event.side_effect = caldav.lib.error.PutError(
            "403 Forbidden\n\nPermission denied"
        )

        with pytest.raises(caldav.lib.error.PutError):
            syncer.synchronise()
