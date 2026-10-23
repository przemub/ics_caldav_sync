FROM python:3.14-alpine

RUN mkdir /app
WORKDIR /app
COPY ics_caldav_sync.py pyproject.toml LICENSE README.md .
# Mount .git for version detection. Ignore uncopied files so we don't get a dirty version.
RUN --mount=source=.git,target=.git,type=bind,rw \
	--mount=type=cache,target=/root/.cache/pip \
	 apk add --no-cache git \
	 && git ls-files -z --deleted | xargs -0 -r git update-index --skip-worktree \
	 && pip install . && apk del git

CMD ics_caldav_sync
