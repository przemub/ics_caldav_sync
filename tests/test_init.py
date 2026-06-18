from unittest.mock import MagicMock

import dateutil.tz
import pytest
import requests.auth

import ics_caldav_sync
from ics_caldav_sync import ICSToCalDAV
from tests.utils import read_fixture

MINIMAL_ICS = "BEGIN:VCALENDAR\r\nVERSION:2.0\r\nPRODID:-//x//x//EN\r\nEND:VCALENDAR\r\n"


@pytest.fixture()
def mocked_clients(monkeypatch):
    """Stub out the network/CalDAV calls __init__ makes so a real instance can
    be constructed without talking to anything."""
    dav = MagicMock()
    monkeypatch.setattr(ics_caldav_sync.caldav, "DAVClient", dav)
    response = MagicMock(text=MINIMAL_ICS)
    get = MagicMock(return_value=response)
    monkeypatch.setattr(ics_caldav_sync.requests, "get", get)
    return dav, get


def base_kwargs(**overrides):
    kwargs = dict(
        remote_url="https://remote.example/cal.ics",
        local_url="https://dav.example/",
        local_calendar_name="cal",
        local_username="user",
        local_password="pass",
    )
    kwargs.update(overrides)
    return kwargs


class TestInit:
    def test_constructs_clients_and_parses_remote(self, mocked_clients):
        dav, get = mocked_clients
        obj = ICSToCalDAV(**base_kwargs(sync_all=True, keep_local=True))

        # Local CalDAV client is built against the local URL with TLS on by
        # default and a basic-auth object derived from the credentials.
        dav.assert_called_once()
        dav_kwargs = dav.call_args.kwargs
        assert dav_kwargs["url"] == "https://dav.example/"
        assert dav_kwargs["ssl_verify_cert"] is True
        assert isinstance(dav_kwargs["auth"], requests.auth.HTTPBasicAuth)
        assert obj.local_client is dav.return_value
        dav.return_value.principal.return_value.calendar.assert_called_once_with("cal")
        assert obj.local_calendar is (
            dav.return_value.principal.return_value.calendar.return_value
        )

        # Remote fetched from the remote URL (TLS on) and parsed to a Calendar.
        get.assert_called_once()
        get_args, get_kwargs = get.call_args
        assert (get_args and get_args[0] or get_kwargs.get("url")) == (
            "https://remote.example/cal.ics"
        )
        assert get_kwargs["verify"] is True
        assert isinstance(get_kwargs["auth"], requests.auth.HTTPBasicAuth)
        assert obj.remote_calendar.name == "VCALENDAR"

        assert obj.sync_all is True
        assert obj.keep_local is True
        assert obj.timezone is None
        assert obj.ignored_compare_fields == []

    def test_tls_verification_flags_are_propagated(self, mocked_clients):
        dav, get = mocked_clients
        ICSToCalDAV(
            **base_kwargs(local_tls_verify=False, remote_tls_verify=False)
        )
        assert dav.call_args.kwargs["ssl_verify_cert"] is False
        assert get.call_args.kwargs["verify"] is False

    def test_timezone_and_ignored_fields_are_parsed(self, mocked_clients):
        obj = ICSToCalDAV(
            **base_kwargs(
                timezone="Europe/Warsaw",
                ignored_compare_fields="DTSTAMP SEQUENCE",
            )
        )
        assert obj.timezone == dateutil.tz.gettz("Europe/Warsaw")
        assert obj.ignored_compare_fields == ["DTSTAMP", "SEQUENCE"]

    def test_invalid_timezone_exits(self, mocked_clients):
        with pytest.raises(SystemExit) as excinfo:
            ICSToCalDAV(**base_kwargs(timezone="Not/AZone"))
        assert excinfo.value.code == 1

    def test_malformed_remote_propagates_parse_error(self, mocked_clients):
        """A corrupt/truncated download must fail loudly rather than being
        silently treated as an empty calendar."""
        _, get = mocked_clients
        get.return_value = MagicMock(text=read_fixture("malformed.ics"))
        with pytest.raises(ValueError):
            ICSToCalDAV(**base_kwargs())
