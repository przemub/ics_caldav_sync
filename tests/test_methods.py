"""Test pure methods."""
import importlib.metadata
from datetime import datetime
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

import caldav.lib.error
import icalendar
import pytest
import requests.auth

import ics_caldav_sync
from ics_caldav_sync import ICSToCalDAV


def make_event(**props) -> icalendar.Event:
    event = icalendar.Event()
    for k, v in props.items():
        event.add(k, v)
    return event


class TestGetAuth:
    def test_basic_returns_basic_auth_with_encoded_credentials(self):
        auth = ICSToCalDAV._get_auth("user", "pass", "basic")
        assert isinstance(auth, requests.auth.HTTPBasicAuth)
        # The basic branch byte-encodes the credentials.
        assert auth.username == b"user"
        assert auth.password == b"pass"

    def test_digest_returns_digest_auth(self):
        auth = ICSToCalDAV._get_auth("user", "pass", "digest")
        assert isinstance(auth, requests.auth.HTTPDigestAuth)
        assert auth.username == "user"
        assert auth.password == "pass"

    def test_invalid_method_raises_value_error(self):
        with pytest.raises(ValueError, match="Invalid authentication method bogus"):
            ICSToCalDAV._get_auth("user", "pass", "bogus")


class TestWrap:
    def test_wraps_vevent_in_vcalendar(self):
        data = ICSToCalDAV._wrap(
            [make_event(summary="X", uid="1", dtstart=datetime(2025, 1, 1, 12))]
        )
        assert isinstance(data, bytes)
        assert data.startswith(b"BEGIN:VCALENDAR")
        assert b"BEGIN:VEVENT" in data
        assert b"Chihiro Software" in data
        # The event's own content must survive the wrapping.
        assert b"SUMMARY:X" in data
        assert b"UID:1" in data
        # Exactly one VEVENT, properly closed inside the calendar.
        assert data.count(b"BEGIN:VEVENT") == 1
        assert data.rstrip().endswith(b"END:VCALENDAR")

    def test_wraps_multiple_events_in_one_calendar(self):
        # A recurring parent and its override share a UID and must land in one
        # resource so neither overwrites the other.
        parent = make_event(summary="Parent", uid="1", dtstart=datetime(2025, 1, 1, 12))
        override = make_event(
            summary="Override", uid="1", dtstart=datetime(2025, 1, 2, 12)
        )
        override.add("RECURRENCE-ID", datetime(2025, 1, 2, 12))

        data = ICSToCalDAV._wrap([parent, override])

        assert data.count(b"BEGIN:VCALENDAR") == 1
        assert data.count(b"BEGIN:VEVENT") == 2
        assert b"SUMMARY:Parent" in data
        assert b"SUMMARY:Override" in data

    def test_adds_missing_timezone(self):
        data = ICSToCalDAV._wrap(
            [
                make_event(
                    summary="X",
                    uid="1",
                    dtstart=datetime(2025, 1, 1, 12, tzinfo=ZoneInfo("Europe/Warsaw")),
                )
            ]
        )
        assert b"BEGIN:VTIMEZONE" in data


class TestMatchesStored:
    @staticmethod
    def matcher(ignored=()):
        obj = object.__new__(ICSToCalDAV)
        obj.ignored_compare_fields = list(ignored)
        return obj

    @staticmethod
    def calendar(*events):
        cal = icalendar.Calendar()
        for event in events:
            cal.add_component(event)
        return cal

    @staticmethod
    def override(**props):
        event = make_event(**props)
        event.add("RECURRENCE-ID", datetime(2025, 1, 2))
        return event

    def test_identical_single_event_matches(self):
        stored = self.calendar(make_event(summary="A", uid="1"))
        assert self.matcher()._matches_stored(stored, [make_event(summary="A", uid="1")])

    def test_changed_event_does_not_match(self):
        stored = self.calendar(make_event(summary="A", uid="1"))
        assert not self.matcher()._matches_stored(
            stored, [make_event(summary="B", uid="1")]
        )

    def test_differing_event_count_does_not_match(self):
        # Stored has only the parent; remote adds an override -> mismatch.
        stored = self.calendar(make_event(summary="A", uid="1"))
        remote = [make_event(summary="A", uid="1"), self.override(summary="A", uid="1")]
        assert not self.matcher()._matches_stored(stored, remote)

    def test_parent_and_override_match_regardless_of_order(self):
        parent = make_event(summary="A", uid="1")
        override = self.override(summary="B", uid="1")
        # Stored lists them in the opposite order to the remote group.
        stored = self.calendar(override, parent)
        assert self.matcher()._matches_stored(stored, [parent, override])

    def test_vtimezone_subcomponents_are_ignored(self):
        # add_missing_timezones() can leave a VTIMEZONE in the stored object; it
        # must not be counted as a VEVENT when matching.
        event = make_event(
            summary="A",
            uid="1",
            dtstart=datetime(2025, 1, 1, 12, tzinfo=ZoneInfo("Europe/Warsaw")),
        )
        stored = self.calendar(event)
        stored.add_missing_timezones()
        assert any(c.name == "VTIMEZONE" for c in stored.subcomponents)
        assert self.matcher()._matches_stored(stored, [event])

    def test_respects_ignored_compare_fields(self):
        stored = self.calendar(
            make_event(summary="A", uid="1", dtstamp=datetime(2025, 1, 1))
        )
        remote = [make_event(summary="A", uid="1", dtstamp=datetime(2025, 6, 1))]
        assert self.matcher(["DTSTAMP"])._matches_stored(stored, remote)
        assert not self.matcher()._matches_stored(stored, remote)


class TestUpdateCapturedNow:
    def test_captured_nows_match_their_names(self):
        # _is_past compares aware event ends against _now_aware; if it were
        # naive, the comparison would raise TypeError.
        obj = object.__new__(ICSToCalDAV)
        obj._update_captured_now()
        assert obj._now_aware.tzinfo is not None
        assert obj._now_aware.tzinfo.utcoffset(obj._now_aware) is not None
        assert obj._now_naive.tzinfo is None


def make_local_event(uid):
    """A mock of a caldav event exposing .icalendar_component.get('uid')."""
    event = MagicMock()
    event.icalendar_component.get.return_value = uid
    return event


@pytest.fixture()
def lister():
    obj = object.__new__(ICSToCalDAV)
    obj.local_calendar = MagicMock()
    return obj


class TestGetLocalEventsIds:
    def test_sync_all_uses_events(self, lister):
        lister.sync_all = True
        lister.local_calendar.events.return_value = [
            make_local_event("A"),
            make_local_event("B"),
        ]

        assert lister._get_local_events_ids() == {"A", "B"}
        lister.local_calendar.events.assert_called_once()
        lister.local_calendar.search.assert_not_called()

    def test_not_sync_all_uses_search(self, lister):
        lister.sync_all = False
        lister.local_calendar.search.return_value = [make_local_event("A")]

        assert lister._get_local_events_ids() == {"A"}
        lister.local_calendar.search.assert_called_once()
        lister.local_calendar.events.assert_not_called()

    def test_report_error_is_reraised(self, lister):
        lister.sync_all = False
        lister.local_calendar.search.side_effect = caldav.lib.error.ReportError

        with pytest.raises(caldav.lib.error.ReportError):
            lister._get_local_events_ids()


class TestGetenvOrRaise:
    def test_returns_value_when_set(self, monkeypatch):
        monkeypatch.setenv("ICS_TEST_VAR", "hello")
        assert ics_caldav_sync.getenv_or_raise("ICS_TEST_VAR") == "hello"

    def test_exits_when_missing(self, monkeypatch, capsys):
        monkeypatch.delenv("ICS_TEST_VAR", raising=False)
        with pytest.raises(SystemExit) as excinfo:
            ics_caldav_sync.getenv_or_raise("ICS_TEST_VAR")
        assert excinfo.value.code == 1
        assert "is unset" in capsys.readouterr().err

    def test_readme_fallback_renders_help_when_package_metadata_missing(
        self, monkeypatch, capsys
    ):
        # Force the README fallback branch by hiding package metadata.
        def raise_not_found(_name):
            raise importlib.metadata.PackageNotFoundError

        monkeypatch.setattr(importlib.metadata, "metadata", raise_not_found)
        monkeypatch.delenv("ICS_TEST_VAR", raising=False)
        with pytest.raises(SystemExit) as excinfo:
            ics_caldav_sync.getenv_or_raise("ICS_TEST_VAR")
        assert excinfo.value.code == 1
        # The README help text must actually be rendered to stdout.
        assert "ICS to CalDAV" in capsys.readouterr().out

    def test_no_help_text_rendered_when_nothing_available(
        self, monkeypatch, capsys
    ):
        # Both metadata and the README are unavailable -> text stays None and
        # nothing is rendered (only the "is unset" message goes to stderr).
        def raise_not_found(_name):
            raise importlib.metadata.PackageNotFoundError

        def raise_file_not_found(*_args, **_kwargs):
            raise FileNotFoundError

        monkeypatch.setattr(importlib.metadata, "metadata", raise_not_found)
        monkeypatch.setattr("builtins.open", raise_file_not_found)
        monkeypatch.delenv("ICS_TEST_VAR", raising=False)
        with pytest.raises(SystemExit) as excinfo:
            ics_caldav_sync.getenv_or_raise("ICS_TEST_VAR")
        assert excinfo.value.code == 1
        captured = capsys.readouterr()
        assert "ICS to CalDAV" not in captured.out
        assert captured.out == ""
