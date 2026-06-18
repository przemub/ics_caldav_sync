"""Test the options parsing in the main method."""
from unittest.mock import MagicMock

import pytest

import ics_caldav_sync

REQUIRED = {
    "REMOTE_URL": "https://example.com/a.ics https://example.com/b.ics",
    "LOCAL_URL": "https://dav.example.com/",
    "LOCAL_CALENDAR_NAME": "cal",
    "LOCAL_USERNAME": "user",
    "LOCAL_PASSWORD": "pass",
}

# Optional vars that main() reads; cleared so the host environment can't leak in.
OPTIONAL = [
    "DEBUG",
    "SYNC_EVERY",
    "SYNC_ALL",
    "KEEP_LOCAL",
    "TIMEZONE",
    "IGNORED_COMPARE_FIELDS",
    "LOCAL_AUTH",
    "REMOTE_AUTH",
    "REMOTE_USERNAME",
    "REMOTE_PASSWORD",
    "LOCAL_TLS_NO_VERIFY",
    "REMOTE_TLS_NO_VERIFY",
]


@pytest.fixture()
def env(monkeypatch):
    for k, v in REQUIRED.items():
        monkeypatch.setenv(k, v)
    for k in OPTIONAL:
        monkeypatch.delenv(k, raising=False)
    return monkeypatch


@pytest.fixture()
def mock_cls(monkeypatch):
    cls = MagicMock()
    monkeypatch.setattr(ics_caldav_sync, "ICSToCalDAV", cls)
    return cls


class TestMainLoop:
    def test_runs_once_per_remote_url_then_breaks(self, env, mock_cls):
        # SYNC_EVERY unset -> single pass over both REMOTE_URLs, then break.
        ics_caldav_sync.main()

        assert mock_cls.call_count == 2
        assert mock_cls.return_value.synchronise.call_count == 2
        remote_urls = [c.kwargs["remote_url"] for c in mock_cls.call_args_list]
        assert remote_urls == [
            "https://example.com/a.ics",
            "https://example.com/b.ics",
        ]

    def test_sleeps_between_runs_when_sync_every_set(self, env, mock_cls):
        env.setenv("REMOTE_URL", "https://example.com/a.ics")
        env.setenv("SYNC_EVERY", "2 minutes")

        class _Stop(Exception):
            pass

        sleep = MagicMock(side_effect=_Stop)
        env.setattr(ics_caldav_sync.time, "sleep", sleep)

        # The loop is infinite; sleep raising breaks out after the first pass.
        with pytest.raises(_Stop):
            ics_caldav_sync.main()

        mock_cls.return_value.synchronise.assert_called_once()
        sleep.assert_called_once()


class TestMainSideEffects:
    def test_debug_enables_debug_logging(self, env, mock_cls):
        env.setenv("DEBUG", "1")
        basic_config = MagicMock()
        env.setattr(ics_caldav_sync.logging, "basicConfig", basic_config)

        ics_caldav_sync.main()

        basic_config.assert_called_once_with(level=ics_caldav_sync.logging.DEBUG)

    def test_debug_unset_does_not_configure_logging(self, env, mock_cls):
        basic_config = MagicMock()
        env.setattr(ics_caldav_sync.logging, "basicConfig", basic_config)

        ics_caldav_sync.main()

        basic_config.assert_not_called()

    def test_disabling_tls_verify_warns_and_silences_urllib3(self, env, mock_cls):
        env.setenv("LOCAL_TLS_NO_VERIFY", "1")
        disable_warnings = MagicMock()
        env.setattr(ics_caldav_sync.urllib3, "disable_warnings", disable_warnings)

        ics_caldav_sync.main()

        disable_warnings.assert_called_once()
        assert mock_cls.call_args.kwargs["local_tls_verify"] is False


class TestMainSyncEveryValidation:
    def test_invalid_sync_every_raises(self, env, mock_cls):
        env.setenv("SYNC_EVERY", "banana")
        with pytest.raises(ValueError, match="SYNC_EVERY value is invalid"):
            ics_caldav_sync.main()
        # Validation happens before any sync.
        mock_cls.assert_not_called()


class TestMainSettingsParsing:
    def test_defaults(self, env, mock_cls):
        ics_caldav_sync.main()

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["local_auth"] == "basic"
        assert kwargs["remote_auth"] == "basic"
        assert kwargs["remote_username"] == ""
        assert kwargs["remote_password"] == ""
        assert kwargs["timezone"] is None
        assert kwargs["ignored_compare_fields"] is None
        assert kwargs["local_tls_verify"] is True
        assert kwargs["remote_tls_verify"] is True

    def test_non_default_values_are_read_from_env(self, env, mock_cls):
        env.setenv("LOCAL_URL", "https://dav.example/")
        env.setenv("LOCAL_CALENDAR_NAME", "My Calendar")
        env.setenv("LOCAL_USERNAME", "alice")
        env.setenv("LOCAL_PASSWORD", "secret")
        env.setenv("LOCAL_AUTH", "digest")
        env.setenv("REMOTE_AUTH", "digest")
        env.setenv("REMOTE_USERNAME", "bob")
        env.setenv("REMOTE_PASSWORD", "hunter2")
        env.setenv("TIMEZONE", "Europe/Warsaw")
        env.setenv("IGNORED_COMPARE_FIELDS", "DTSTAMP SEQUENCE")

        ics_caldav_sync.main()

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["local_url"] == "https://dav.example/"
        assert kwargs["local_calendar_name"] == "My Calendar"
        assert kwargs["local_username"] == "alice"
        assert kwargs["local_password"] == "secret"
        assert kwargs["local_auth"] == "digest"
        assert kwargs["remote_auth"] == "digest"
        assert kwargs["remote_username"] == "bob"
        assert kwargs["remote_password"] == "hunter2"
        assert kwargs["timezone"] == "Europe/Warsaw"
        assert kwargs["ignored_compare_fields"] == "DTSTAMP SEQUENCE"

    def test_sync_all_truthiness_is_buggy(self, env, mock_cls):
        # Documents a latent bug: bool(os.getenv("SYNC_ALL", False)) is True for
        # ANY non-empty string, including "0"/"false". See plan follow-ups.
        env.setenv("SYNC_ALL", "0")
        env.setenv("KEEP_LOCAL", "false")
        ics_caldav_sync.main()

        kwargs = mock_cls.call_args.kwargs
        assert kwargs["sync_all"] is True
        assert kwargs["keep_local"] is True
