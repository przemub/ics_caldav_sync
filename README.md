# ICS to CalDAV synchronisation

[![PyPI version](https://badge.fury.io/py/ics-caldav-sync.svg)](https://pypi.org/project/ics-caldav-sync/)
[![Docker Pulls](https://img.shields.io/docker/pulls/przemub/ics_caldav_sync)](https://hub.docker.com/r/przemub/ics_caldav_sync)
[![Licence](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

Downloads a calendar in ICS format and uploads it to a CalDAV server, regularly.
Your employee, school, or whoever shares a calendar as a link to an ICS file,
and you'd like to have it on another CalDAV server?
Look no further.

## Standalone usage

Install the script with `pip install ics_caldav_sync`
(or, if installing from source, `pip install .`) 
and run `ics_caldav_sync` script which should be on your PATH now.
Python 3.9 or higher is required.

There also exist `Dockerfile` and `docker-compose.yml` files so you can
run it on your Docker server.

The Docker images are published to [Docker Hub](https://hub.docker.com/r/przemub/ics_caldav_sync),
repository `przemub/ics_caldav_sync` tagged by short commit hashes and versions.

Set the settings as environment variables:

| Variable              | Type    | Required | Default | Description                                                                                                  |
|-----------------------|---------|----------|---------|--------------------------------------------------------------------------------------------------------------|
| `REMOTE_URL`          | string  | Yes      | -       | ICS file URL. You can provide multiple URLs, separated by a space character.                                 |
| `LOCAL_URL`           | string  | Yes      | -       | CalDAV server URL.                                                                                           |
| `LOCAL_CALENDAR_NAME` | string  | Yes      | -       | The name of your CalDAV calendar.                                                                            |
| `LOCAL_USERNAME`      | string  | Yes      | -       | CalDAV username.                                                                                             |
| `LOCAL_PASSWORD`      | string  | Yes      | -       | CalDAV password.                                                                                             |
| `LOCAL_AUTH`          | string  | No       | `basic` | CalDAV authentication method (either `basic` or `digest`).                                                   |
| `REMOTE_USERNAME`     | string  | No       | -       | ICS host username.                                                                                           |
| `REMOTE_PASSWORD`     | string  | No       | -       | ICS host password.                                                                                           |
| `REMOTE_AUTH`         | string  | No       | `basic` | ICS host authentication method (either `basic` or `digest`).                                                 |
| `TIMEZONE`            | string  | No       | -       | Override events timezone. Examples: `Utc`, `Europe/Warsaw`, `Asia/Tokyo`.                                    |
| `SYNC_EVERY`          | string  | No       | -       | How often should the synchronisation occur? Examples: `2 minutes`, `1 hour`. Synchronise once if empty.      |
| `DEBUG`               | boolean | No       | `false` | Set to any non-empty value to print debugging messages. Please set this when reporting an error.             |
| `SYNC_ALL`            | boolean | No       | `false` | If set, all events in the calendar will be synced. Otherwise, only the ones occurring in the future will be. |
| `KEEP_LOCAL`          | boolean | No       | `false` | Do not delete events on the CalDAV server that do not exist in the ICS file.                                 |

## Library usage

This script can be also used as a library in your Python script using `ICSToCalDAVSync`
class and its `synchronise` method.
```
from ics_caldav_sync import ICSToCalDAVSync

sync = ICSToCalDAVSync(
    remote_url="https://example.com/calendar.ics",
    local_url="https://caldav.example.com",
    local_calendar_name="My Calendar",
    local_username="username",
    local_password="password",
    # remote_username="",
    # remote_password="",
    # remote_auth="basic|digest",
    # sync_all=False,
    # keep_local=False
    # timezone=None,
)

sync.synchronise()
```

## Examples

### Command-line usage

`ics_caldav_sync` can be used from the command line when installed with `pip`. An example:

```shell
REMOTE_URL=https://example.com/path/to/calendar_file.ics \
  LOCAL_URL=https://example.net/caldav \
  LOCAL_CALENDAR_NAME="My Calendar" \
  LOCAL_USERNAME=myusername \
  LOCAL_PASSWORD=mypassword \
  ics_caldav_sync
```

### Docker

You can also do the same as a Docker one-liner - to avoid installing dependencies yourself.

```shell
docker run --rm \
  -e REMOTE_URL=https://example.com/path/to/calendar_file.ics \
  -e LOCAL_URL=https://example.net/caldav \
  -e LOCAL_CALENDAR_NAME="My Calendar" \
  -e LOCAL_USERNAME=myusername \
  -e LOCAL_PASSWORD=mypassword \
  przemub/ics_caldav_sync
```

### Docker Compose

When setting up a long-running, periodic sync, Docker Compose can be helpful.

This example also shows settings needed by a CalDAV server [Baïkal](https://sabre.io/baikal/).

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

## Tested with

On the local side (CalDAV server):
- [Baïkal](https://sabre.io/baikal/)
- [Radicale](https://radicale.org/v3.html)

On the remote site (ICS file generator):
- [Google Calendar](https://support.google.com/calendar/answer/37083)
- [Microsoft Outlook](https://support.microsoft.com/en-gb/office/share-your-calendar-in-outlook-2fcf4f4f-8d46-4d8b-ae79-5d94549e531b)

Please feel free to open a PR against this section to add your configuration!

## Rationale

In my case, my new shiny Bluetooth wristwatch, Casio Edifice ECB-10,
did not support synchronisation with [calendar subscriptions](https://support.apple.com/en-us/HT202361).
And so this script was created.
