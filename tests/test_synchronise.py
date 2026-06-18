"""Unit-test the synchronise method."""
from datetime import date, datetime, timedelta, timezone
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


class TestSynchroniseOrdersRecurrence:
    def test_parent_saved_before_recurrence_override(self, syncer):
        """A recurrence override (RECURRENCE-ID) must be saved after its
        parent, even when the ICS lists it first."""
        parent = make_event(summary="Parent", uid="123", dtstamp=datetime(2025, 1, 1))
        override = make_event(summary="Override", uid="123", dtstamp=datetime(2025, 1, 1))
        override.add("RECURRENCE-ID", datetime(2025, 1, 2))
        # Deliberately out of order: override first.
        type(syncer.remote_calendar).events = PropertyMock(return_value=[override, parent])
        syncer.local_calendar.get_event_by_uid.side_effect = caldav.lib.error.NotFoundError

        syncer.synchronise()

        saved = [call.args[0] for call in syncer.local_calendar.save_event.call_args_list]
        assert len(saved) == 2
        assert b"RECURRENCE-ID" not in saved[0]
        assert b"RECURRENCE-ID" in saved[1]


class TestSynchronisePastEventFiltering:
    """When sync_all is off, events that have already ended are skipped.

    The fixture defaults to sync_all=True, which bypasses this whole block, so
    each test here flips it off. Dates are deliberately far in the past (2000)
    or future (2099) so the result never depends on the wall clock.
    """

    def _run(self, syncer, event):
        syncer.sync_all = False
        type(syncer.remote_calendar).events = PropertyMock(return_value=[event])
        syncer.local_calendar.get_event_by_uid.side_effect = (
            caldav.lib.error.NotFoundError
        )
        syncer.synchronise()

    # All-day events: end is a date.
    def test_all_day_past_skipped(self, syncer):
        event = make_event(uid="1", dtstart=date(2000, 1, 1), dtend=date(2000, 1, 2))
        self._run(syncer, event)
        syncer.local_calendar.save_event.assert_not_called()

    def test_all_day_future_saved(self, syncer):
        event = make_event(uid="1", dtstart=date(2099, 1, 1), dtend=date(2099, 1, 2))
        self._run(syncer, event)
        syncer.local_calendar.save_event.assert_called_once()

    def test_all_day_ending_today_is_kept(self, syncer):
        # Boundary: the filter is `today > end`, so an event ending exactly
        # today is NOT in the past and must be saved.
        today = date.today()
        event = make_event(uid="1", dtstart=today, dtend=today)
        self._run(syncer, event)
        syncer.local_calendar.save_event.assert_called_once()

    def test_all_day_ending_yesterday_is_skipped(self, syncer):
        yesterday = date.today() - timedelta(days=1)
        event = make_event(uid="1", dtstart=yesterday, dtend=yesterday)
        self._run(syncer, event)
        syncer.local_calendar.save_event.assert_not_called()

    # Naive datetimes: compared against datetime.now().
    def test_naive_past_skipped(self, syncer):
        event = make_event(
            uid="1", dtstart=datetime(2000, 1, 1, 12), dtend=datetime(2000, 1, 1, 13)
        )
        self._run(syncer, event)
        syncer.local_calendar.save_event.assert_not_called()

    def test_naive_future_saved(self, syncer):
        event = make_event(
            uid="1", dtstart=datetime(2099, 1, 1, 12), dtend=datetime(2099, 1, 1, 13)
        )
        self._run(syncer, event)
        syncer.local_calendar.save_event.assert_called_once()

    # Aware datetimes: compared against datetime.now(timezone.utc).
    def test_aware_past_skipped(self, syncer):
        event = make_event(
            uid="1",
            dtstart=datetime(2000, 1, 1, 12, tzinfo=timezone.utc),
            dtend=datetime(2000, 1, 1, 13, tzinfo=timezone.utc),
        )
        self._run(syncer, event)
        syncer.local_calendar.save_event.assert_not_called()

    def test_aware_future_saved(self, syncer):
        event = make_event(
            uid="1",
            dtstart=datetime(2099, 1, 1, 12, tzinfo=timezone.utc),
            dtend=datetime(2099, 1, 1, 13, tzinfo=timezone.utc),
        )
        self._run(syncer, event)
        syncer.local_calendar.save_event.assert_called_once()


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
