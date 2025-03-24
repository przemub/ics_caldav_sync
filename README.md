# ICS to CalDAV synchronisation

Downloads a calendar in ICS format and uploads it to a CalDAV server, regularly.
Your employee, school, or whoever shares a calendar as a link to an ICS file
and you'd like to have it on another CalDAV server?
Look no further.

## Standalone usage

Install the script with `pip install .` and run `ics_caldav_sync` script
which should be on your PATH now.

There also exist `Dockerfile` and `docker-compose.yml` files so you can
run it on your Docker server.

Set the settings as environment variables:
* REMOTE_URL (str): ICS file URL.
* LOCAL_URL (str): CalDAV URL.
* LOCAL_CALENDAR_NAME (str): The name of your CalDAV calendar.
* LOCAL_USERNAME (str): CalDAV username.
* LOCAL_PASSWORD (str): CalDAV password.
* LOCAL_AUTH (str, optional): CalDAV authentication method (either basic or digest). Default: basic.
* REMOTE_USERNAME (str, optional): ICS host username.
* REMOTE_PASSWORD (str, optional): ICS host password.
* REMOTE_AUTH (str, optional): ICS host authentication method (either basic or digest). Default: basic.
* TIMEZONE (str, optional): Override events timezone. (Example timezones: Utc, Europe/Warsaw, Asia/Tokyo).
* SYNC_EVERY (str): How often should the synchronisation occur? For example: 2 minutes, 1 hour. Synchronise once if empty.
* DEBUG (bool, optional): Set to anything to print debugging messages. Please set this when reporting an error.
* SYNC_ALL (bool, optional): If set, all events in the calendar will be synced. Otherwise, only the ones occuring in the future will be.
* KEEP_LOCAL (bool, optional): Do not delete events on the CalDAV server that do not exist in the ICS file.

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
        local_auth: str = "basic",
        remote_username: str = "",
        remote_password: str = "",
        remote_auth: str = "basic",
        sync_all: bool = False,
        keep_local: bool = False,
        timezone: str | None = None,
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

## Examples

### Docker-compose and Baikal

```yaml
services:
  ics_caldav_sync:
    image: ics_caldav_sync
    restart: unless-stopped
    environment:
      - REMOTE_URL=https://example.com/path/to/calendar_file.ics
      - LOCAL_URL=https://baikal.myserver.com/dav.php/
      - LOCAL_CALENDAR_NAME=My Calendar
      - LOCAL_USERNAME=myusername
      - LOCAL_PASSWORD=mypassword
      - LOCAL_AUTH=digest  # Required by Baikal - try removing if getting Unauthorized error
      - SYNC_EVERY=30 minutes
```

### Command-line usage

`ics_caldav_sync` can be also used from the command line. An example:

```shell
REMOTE_URL=https://example.com/path/to/calendar_file.ics \
  LOCAL_URL=https://baikal.myserver.com/dav.php \
  LOCAL_CALENDAR_NAME="My Calendar" \
  LOCAL_USERNAME=myusername \
  LOCAL_PASSWORD=mypassword \
  ics_caldav_sync
```

## Rationale

In my case, my new shiny Bluetooth wristwatch, Casio Edifice ECB-10,
did not support synchronisation with [calendar subscriptions](https://support.apple.com/en-us/HT202361).
And so this script was created.
