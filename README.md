# ICS to CalDAV synchronisation

Downloads a calendar in ICS format and uploads it to a CalDAV server, regularly.
Your employee, school, or whoever shares a calendar as a link to an ICS file
and you'd like to have it on another CalDAV server?
Look no further.

## Standalone usage

Install requirements from `requirements.txt` and run `ics_caldav_sync.py` file
using Python 3.8 or higher.

There exist also `Dockerfile` and `docker-compose.yml` files so you can
run it on your Docker server.

Set the settings as environment variables:
* REMOTE_URL (str): ICS file URL.
* LOCAL_URL (str): CalDAV URL.
* LOCAL_CALENDAR_NAME (str): The name of your CalDAV calendar.
* LOCAL_USERNAME (str): CalDAV username.
* LOCAL_PASSWORD (str): CalDAV password.
* REMOTE_USERNAME (str, optional): ICS host username.
* REMOTE_PASSWORD (str, optional): ICS host password.
* SYNC_EVERY (str): How often should the synchronisation occur? For example: 2 minutes, 1 hour. Synchronise once if empty.
* DEBUG (bool, optional): Set to anything to print debugging messages. Please set this when reporting an error.
* SYNC_ALL (bool, optional): If set, all events in the calendar will be synced. Otherwise, only the ones occuring in the future will be.

## Library usage

This script can be also used as a library in your Python script using `ICSToCalDAVSync`
class and its `synchronise` method.
```
    def ICSToCalDAVSync.__init__(
        self,
        *,
        remote_url: str,
        local_url: str,
        local_calendar_name: str,
        local_username: str,
        local_password: str,
        remote_username: str = "",
        remote_password: str = "",
        sync_all: bool = False
    )

    def ICSToCalDavSync.synchronise(self):
        """
        The main function which:
        1) Pulls the events from the remote calendar,
        2) Saves them into the local calendar,
        3) Removes local events which are not in the remote any more.

        If sync_all is set, all events will be pulled. Otherwise, only
        the ones occuring after now will be.
        """
```

## Rationale

In my case, my new shiny Bluetooth wristwatch, Casio Edifice ECB-10,
did not support synchronisation with [calendar subscriptions](https://support.apple.com/en-us/HT202361).
And so this script was created.
