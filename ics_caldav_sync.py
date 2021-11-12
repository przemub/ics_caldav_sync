import os
import sys
import time

import arrow
import caldav
import ics
import requests


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
    """

    def __init__(
        self,
        *,
        remote_url: str,
        local_url: str,
        local_calendar_name: str,
        local_username: str,
        local_password: str,
        remote_username: str = "",
        remote_password: str = "",
    ):
        self.local_client = caldav.DAVClient(
            url=local_url,
            auth=(local_username.encode(), local_password.encode()),
        )

        self.local_calendar = self.local_client.principal().calendar(
            local_calendar_name
        )
        self.remote_calendar = ics.Calendar(
            requests.get(
                remote_url,
                auth=(remote_username.encode(), remote_password.encode()),
            ).text
        )

    def _get_local_events_ids(self) -> set[int]:
        """
        This piece of crap:
        1) Gets from the local calendar all the events ocurring after now,
        2) Loads them to ics library so their UID can be pulled,
        3) Pulls all of the UIDs and returns them.
        """
        local_events = self.local_calendar.date_search(arrow.utcnow())
        local_events_ids = set(
            next(iter(ics.Calendar(e.data).events)).uid for e in local_events
        )
        return local_events_ids

    @staticmethod
    def _wrap(vevent: str) -> str:
        """
        Since CalDAV expects a VEVENT in a VCALENDAR,
        we need to wrap each event pulled from a single ICS
        into its own calendar.
        """
        return f"""BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//Chihiro Software Ltd//Calendar sync//EN
{vevent}
END:VCALENDAR
"""

    def synchronise(self):
        """
        The main function which:
        1) Pulls all the events from the remote calendar,
        2) Saves them into the local calendar,
        3) Removes local events which are not in the remote any more.
        """
        for remote_event in self.remote_calendar.events:
            if arrow.utcnow() > remote_event.end:
                continue

            self.local_calendar.save_event(self._wrap(remote_event))
            print("+", end="")
            sys.stdout.flush()
        print()

        remote_events_ids = set(e.uid for e in self.remote_calendar.events)
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
        raise Exception(f"Environment variable {var} is unset")
    return value


if __name__ == "__main__":
    settings = {
        "remote_url": getenv_or_raise("REMOTE_URL"),
        "local_url": getenv_or_raise("LOCAL_URL"),
        "local_calendar_name": getenv_or_raise("LOCAL_CALENDAR_NAME"),
        "local_username": getenv_or_raise("LOCAL_USERNAME"),
        "local_password": getenv_or_raise("LOCAL_PASSWORD"),
        "remote_username": os.getenv("REMOTE_USERNAME", ""),
        "remote_password": os.getenv("REMOTE_PASWORD", ""),
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
