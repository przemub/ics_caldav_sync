#!/usr/bin/env python
import datetime
import logging
import os
import pathlib
import sys
import time

import arrow
import caldav
import caldav.lib.error
import dateutil.tz
import icalendar
import requests
import requests.auth
import vobject.base
import x_wr_timezone


logger = logging.getLogger(__name__)


class ICSToCalDAV:
    """
    Downloads a calendar in ICS format and uploads it to a CalDAV server.
    Your employee, school, or whoever shares a calendar as an ICS file
    and you'd like to have it on another CalDAV server?
    Look no further.

    Arguments:
    * remote_url (str): ICS file URL.
    * local_url (str): CalDAV URL.
    * local_calendar_name (str): The name of your CalDAV calendar.
    * local_username (str): CalDAV username.
    * local_password (str): CalDAV password.
    * remote_username (str, optional): ICS host username.
    * remote_password (str, optional): ICS host password.
    * sync_all (bool, optional): Sync past events.
    * keep_local (bool, optional): Do not delete events on the CalDAV server that do not exist in the ICS file.
    * timezone (str, optional): Override events timezone. See: https://dateutil.readthedocs.io/en/stable/tz.html
    """

    def __init__(
        self,
        *,
        remote_url: str,
        local_url: str,
        local_calendar_name: str,
        local_username: str,
        local_password: str,
        local_auth: str = "basic",
        remote_username: str = "",
        remote_password: str = "",
        remote_auth: str = "basic",
        sync_all: bool = False,
        keep_local: bool = False,
        timezone: str | None = None,
    ):
        self.timezone = dateutil.tz.gettz(timezone) \
            if timezone is not None else None
        if timezone and self.timezone is None:
            logger.critical("Timezone %s does not exist.", timezone)
            sys.exit(1)

        self.local_client = caldav.DAVClient(
            url=local_url,
            auth=self._get_auth(local_username, local_password, local_auth)
        )

        self.local_calendar = self.local_client.principal().calendar(
            local_calendar_name
        )

        remote_calendar = icalendar.Calendar.from_ical(
            requests.get(
                remote_url,
                auth=self._get_auth(remote_username, remote_password, remote_auth)
            ).text
        )

        # Fix timezones
        self.remote_calendar = x_wr_timezone.to_standard(
            remote_calendar,
            self.timezone
        )

        self.sync_all = sync_all
        self.keep_local = keep_local

    @staticmethod
    def _get_auth(username: str, password: str, method: str) -> requests.auth.AuthBase:
        """
        Get a requests auth instance from given username, password and
        authentication method.
        Supported methods: "basic", "digest".
        """
        if method == "basic":
            return requests.auth.HTTPBasicAuth(
                username.encode(),
                password.encode(),
            )
        if method == "digest":
            return requests.auth.HTTPDigestAuth(
                username,
                password
            )
        raise ValueError("Invalid authentication method %s", method)

    def _get_local_events_ids(self) -> set[str]:
        """
        This piece of crap:
        1) Gets from the local calendar all the events occurring after now,
        2) Loads them to ics library so their UID can be pulled,
        3) Pulls all the UIDs and returns them.

        If sync_all is set, then all events will be pulled.
        """
        if self.sync_all:
            local_events = self.local_calendar.events()
        else:
            try:
                local_events = self.local_calendar.search(start=arrow.utcnow())
            except caldav.lib.error.ReportError:
                logger.critical("Server failed when filtering events. Try SYNC_ALL=1 to do a full sync.")
                raise
        local_events_ids = set(
            e.icalendar_component.get("uid") for e in local_events
        )
        return local_events_ids

    @staticmethod
    def _wrap(vevent: icalendar.Event) -> bytes:
        """
        Since CalDAV expects a VEVENT in a VCALENDAR,
        we need to wrap each event pulled from a single ICS
        into its own calendar.
        This is then serialized, so it's ready to be sent
        via CalDAV.
        """
        calendar = icalendar.Calendar(
            prodid="-//Chihiro Software Ltd//NONSGML Calendar sync//EN"
        )
        calendar.add_component(vevent)
        calendar.add_missing_timezones()

        data = calendar.to_ical()
        logger.debug("Serialized event:\n%s", data)

        return data

    def synchronise(self):
        """
        The main function which:
        1) Pulls the events from the remote calendar,
        2) Saves them into the local calendar,
        3) Removes local events which are not in the remote any more.

        If sync_all is set, all events will be pulled. Otherwise, only
        the ones occurring after now will be.
        """
        now_naive = datetime.datetime.now()
        now_aware = datetime.datetime.now(datetime.timezone.utc)
        today = datetime.date.today()

        for remote_event in self.remote_calendar.events:
            # Skip events in the past, unless requested not to.
            if not self.sync_all:
                end = remote_event.end
                # Compare against date, or naive- or aware- datetime
                # https://docs.python.org/3/library/datetime.html#determining-if-an-object-is-aware-or-naive
                if isinstance(end, datetime.date) and not isinstance(end, datetime.datetime):
                    if today > end:
                        continue
                elif end.tzinfo is not None and end.tzinfo.utcoffset(end) is not None:
                    if now_aware > end:
                        continue
                else:
                    if now_naive > end:
                        continue

            try:
                self.local_calendar.save_event(self._wrap(remote_event))
            except vobject.base.ValidateError:
                logger.exception("Invalid event was downloaded from the remote. It will be skipped.")
            print("+", end="")
            sys.stdout.flush()
        print()

        if not self.keep_local:
            # Delete local events that don't exist in the remote
            remote_events_ids = set(e["UID"] for e in self.remote_calendar.events)
            events_to_delete = self._get_local_events_ids() - remote_events_ids
            for local_event_id in events_to_delete:
                self.local_client.delete(
                    f"{self.local_calendar.url}{local_event_id}.ics"
                )
                print("-", end="")
                sys.stdout.flush()
        print()


def getenv_or_raise(var):
    if (value := os.getenv(var)) is None:
        print(f"\033[1mEnvironment variable {var} is unset.\033[0m\n", file=sys.stderr)
        # Printing help text
        with open(pathlib.Path(__file__).parent / "README.md") as f:
            print(f.read(), file=sys.stderr)
        sys.exit(1)
    return value


def main():
    if os.getenv("DEBUG"):
        logging.basicConfig(level=logging.DEBUG)

    settings = {
        "remote_url": getenv_or_raise("REMOTE_URL"),
        "local_url": getenv_or_raise("LOCAL_URL"),
        "local_calendar_name": getenv_or_raise("LOCAL_CALENDAR_NAME"),
        "local_username": getenv_or_raise("LOCAL_USERNAME"),
        "local_password": getenv_or_raise("LOCAL_PASSWORD"),
        "local_auth": os.getenv("LOCAL_AUTH", "basic"),
        "remote_username": os.getenv("REMOTE_USERNAME", ""),
        "remote_password": os.getenv("REMOTE_PASSWORD", ""),
        "remote_auth": os.getenv("REMOTE_AUTH", "basic"),
        "sync_all": bool(os.getenv("SYNC_ALL", False)),
        "keep_local": bool(os.getenv("KEEP_LOCAL", False)),
        "timezone": os.getenv("TIMEZONE") or None,
    }

    sync_every = os.getenv("SYNC_EVERY", None)
    if sync_every is not None:
        sync_every = "in " + sync_every
        try:
            arrow.utcnow().dehumanize(sync_every)
        except ValueError as ve:
            raise ValueError(
                "SYNC_EVERY value is invalid. Try something like '2 minutes' or '1 hour'"
            ) from ve

    while True:
        if sync_every is None:
            next_run = None
        else:
            next_run = arrow.utcnow().dehumanize(sync_every)

        ICSToCalDAV(**settings).synchronise()

        if next_run is None:
            break
        else:
            seconds_to_next = (next_run - arrow.utcnow()).total_seconds()
            if seconds_to_next > 0:
                time.sleep(seconds_to_next)


if __name__ == "__main__":
    main()
