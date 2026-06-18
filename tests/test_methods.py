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
            make_event(summary="X", uid="1", dtstart=datetime(2025, 1, 1, 12))
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

    def test_adds_missing_timezone(self):
        data = ICSToCalDAV._wrap(
            make_event(
                summary="X",
                uid="1",
                dtstart=datetime(2025, 1, 1, 12, tzinfo=ZoneInfo("Europe/Warsaw")),
            )
        )
        assert b"BEGIN:VTIMEZONE" in data


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
