FROM python:3.13

RUN mkdir /app
WORKDIR /app
COPY . .
# Mount .git for version detection
RUN --mount=source=.git,target=.git,type=bind \
	pip install .

CMD ics_caldav_sync
