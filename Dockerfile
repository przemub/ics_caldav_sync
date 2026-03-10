FROM python:3.13-alpine

RUN mkdir /app
WORKDIR /app
COPY ics_caldav_sync.py pyproject.toml LICENSE README.md .
# Mount .git for version detection
RUN --mount=source=.git,target=.git,type=bind \
	--mount=type=cache,target=/root/.cache/pip \
	 apk add --no-cache git && pip install . && apk del git

CMD ics_caldav_sync
