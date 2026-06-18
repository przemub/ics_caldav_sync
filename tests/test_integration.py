"""End-to-end tests against a real, in-process Radicale CalDAV server.

The module is skipped entirely if ``radicale``
is unavailable.
"""
import threading
import wsgiref.simple_server
from datetime import date, datetime, timezone
from unittest.mock import MagicMock

import caldav
import icalendar
import pytest

from ics_caldav_sync import ICSToCalDAV
from tests.utils import load_fixture

radicale = pytest.importorskip("radicale")
import radicale.config  # noqa: E402

pytestmark = pytest.mark.integration

USERNAME = "test"
PASSWORD = "test"


class _QuietHandler(wsgiref.simple_server.WSGIRequestHandler):
    def log_message(self, *args):  # silence per-request stderr logging
        pass


@pytest.fixture()
def caldav_url(tmp_path):
    """Start a throwaway Radicale server on an ephemeral port."""
    htpasswd = tmp_path / "users"
    htpasswd.write_text(f"{USERNAME}:{PASSWORD}\n")

    configuration = radicale.config.load()
    configuration.update(
        {
            "storage": {"filesystem_folder": str(tmp_path / "collections")},
            "auth": {
                "type": "htpasswd",
                "htpasswd_filename": str(htpasswd),
                "htpasswd_encryption": "plain",
            },
        },
        "test",
    )

    app = radicale.Application(configuration)
    httpd = wsgiref.simple_server.make_server(
        "127.0.0.1", 0, app, handler_class=_QuietHandler
    )
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/"
    finally:
        httpd.shutdown()
        thread.join()


def make_syncer(caldav_url, *, sync_all=True, keep_local=True):
    """A real ICSToCalDAV wired to a real CalDAV calendar, but with the remote
    set directly so __init__'s network fetch is bypassed."""
    client = caldav.DAVClient(url=caldav_url, username=USERNAME, password=PASSWORD)
    calendar = client.principal().make_calendar(name="integration")

    syncer = object.__new__(ICSToCalDAV)
    syncer.ignored_compare_fields = []
    syncer.sync_all = sync_all
    syncer.keep_local = keep_local
    syncer.local_client = client
    syncer.local_calendar = calendar
    return syncer


def make_event(**props) -> icalendar.Event:
    event = icalendar.Event()
    for k, v in props.items():
        event.add(k, v)
    return event


def remote(*events) -> icalendar.Calendar:
    cal = icalendar.Calendar()
    for event in events:
        cal.add_component(event)
    return cal


def stored_uids(syncer):
    return {e.icalendar_component.get("uid") for e in syncer.local_calendar.events()}


def stored_components(syncer):
    return [e.icalendar_component for e in syncer.local_calendar.events()]


def stored_vevents(syncer):
    """Every VEVENT across every stored object, flattened."""
    vevents = []
    for event in syncer.local_calendar.events():
        for sub in event.icalendar_instance.subcomponents:
            if sub.name == "VEVENT":
                vevents.append(sub)
    return vevents


class TestUpload:
    def test_single_event_is_uploaded(self, caldav_url):
        syncer = make_syncer(caldav_url)
        syncer.remote_calendar = remote(
            make_event(
                summary="Meeting",
                uid="one@test",
                dtstart=datetime(2099, 1, 1, 12),
                dtend=datetime(2099, 1, 1, 13),
                dtstamp=datetime(2025, 1, 1),
            )
        )

        syncer.synchronise()

        components = stored_components(syncer)
        assert len(components) == 1
        assert str(components[0].get("summary")) == "Meeting"

    def test_multiple_events_are_uploaded(self, caldav_url):
        syncer = make_syncer(caldav_url)
        syncer.remote_calendar = remote(
            make_event(
                summary="A",
                uid="a@test",
                dtstart=datetime(2099, 1, 1, 12),
                dtend=datetime(2099, 1, 1, 13),
                dtstamp=datetime(2025, 1, 1),
            ),
            make_event(
                summary="B",
                uid="b@test",
                dtstart=datetime(2099, 2, 1, 12),
                dtend=datetime(2099, 2, 1, 13),
                dtstamp=datetime(2025, 1, 1),
            ),
        )

        syncer.synchronise()

        assert stored_uids(syncer) == {"a@test", "b@test"}

    def test_all_day_event_round_trips(self, caldav_url):
        syncer = make_syncer(caldav_url)
        syncer.remote_calendar = load_fixture("all_day.ics")

        syncer.synchronise()

        (component,) = stored_components(syncer)
        assert isinstance(component.start, date)
        assert not isinstance(component.start, datetime)

    def test_timezone_aware_event_round_trips(self, caldav_url):
        syncer = make_syncer(caldav_url)
        syncer.remote_calendar = load_fixture("vtimezone.ics")

        syncer.synchronise()

        (component,) = stored_components(syncer)
        end = component.end
        assert end.tzinfo is not None
        assert end.tzinfo.utcoffset(end) is not None


class TestUpdate:
    def test_changed_event_is_updated_in_place(self, caldav_url):
        syncer = make_syncer(caldav_url)

        def event(summary):
            return remote(
                make_event(
                    summary=summary,
                    uid="u@test",
                    dtstart=datetime(2099, 1, 1, 12),
                    dtend=datetime(2099, 1, 1, 13),
                    dtstamp=datetime(2025, 1, 1),
                )
            )

        syncer.remote_calendar = event("Original")
        syncer.synchronise()
        syncer.remote_calendar = event("Updated")
        syncer.synchronise()

        components = stored_components(syncer)
        # Updated in place: exactly one event, with the new summary.
        assert len(components) == 1
        assert str(components[0].get("summary")) == "Updated"

    def test_resync_skips_identical_event(self, caldav_url):
        """A second sync of unchanged data must not re-upload anything; this
        only holds if _compare still matches the server's stored copy."""
        syncer = make_syncer(caldav_url)
        syncer.remote_calendar = remote(
            make_event(
                summary="Stable",
                uid="s@test",
                dtstart=datetime(2099, 1, 1, 12),
                dtend=datetime(2099, 1, 1, 13),
                dtstamp=datetime(2025, 1, 1),
            )
        )
        syncer.synchronise()

        # Spy on the real save to prove the second pass writes nothing.
        spy = MagicMock(wraps=syncer.local_calendar.save_event)
        syncer.local_calendar.save_event = spy
        syncer.synchronise()

        spy.assert_not_called()
        assert len(stored_components(syncer)) == 1


class TestDeletion:
    def test_stale_events_are_deleted(self, caldav_url):
        syncer = make_syncer(caldav_url, keep_local=False)
        syncer.remote_calendar = load_fixture("all_day.ics")
        syncer.synchronise()
        assert syncer.local_calendar.events(), "expected the event to be uploaded"

        # Second sync with an empty remote should delete it.
        syncer.remote_calendar = icalendar.Calendar()
        syncer.synchronise()
        assert syncer.local_calendar.events() == []

    def test_keep_local_preserves_stale_events(self, caldav_url):
        syncer = make_syncer(caldav_url, keep_local=True)
        syncer.remote_calendar = load_fixture("all_day.ics")
        syncer.synchronise()
        assert len(syncer.local_calendar.events()) == 1

        # With keep_local set, an empty remote must NOT remove the event.
        syncer.remote_calendar = icalendar.Calendar()
        syncer.synchronise()
        assert len(syncer.local_calendar.events()) == 1


class TestRecurrence:
    @pytest.mark.xfail(
        strict=True,
        reason="Known bug: a recurring parent and its RECURRENCE-ID override "
        "share a UID, but synchronise() saves each wrapped event separately to "
        "<uid>.ics, so the override's PUT overwrites the parent and the whole "
        "recurring series is lost. They should be stored together in one "
        "VCALENDAR resource.",
    )
    def test_recurring_event_and_override_both_survive(self, caldav_url):
        syncer = make_syncer(caldav_url)
        syncer.remote_calendar = load_fixture("recurring_with_override.ics")

        syncer.synchronise()

        vevents = stored_vevents(syncer)
        assert any("RRULE" in v for v in vevents), (
            "the recurring parent series must survive"
        )
        assert any(v.get("RECURRENCE-ID") is not None for v in vevents), (
            "the recurrence override must survive"
        )


class TestPastEventFiltering:
    def test_past_events_skipped_when_not_sync_all(self, caldav_url):
        syncer = make_syncer(caldav_url, sync_all=False)
        syncer.remote_calendar = remote(
            make_event(
                summary="Past",
                uid="past@test",
                dtstart=datetime(2000, 1, 1, 12, tzinfo=timezone.utc),
                dtend=datetime(2000, 1, 1, 13, tzinfo=timezone.utc),
                dtstamp=datetime(2025, 1, 1),
            ),
            make_event(
                summary="Future",
                uid="future@test",
                dtstart=datetime(2099, 1, 1, 12, tzinfo=timezone.utc),
                dtend=datetime(2099, 1, 1, 13, tzinfo=timezone.utc),
                dtstamp=datetime(2025, 1, 1),
            ),
        )

        syncer.synchronise()

        assert stored_uids(syncer) == {"future@test"}
