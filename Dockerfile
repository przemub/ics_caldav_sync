FROM python:3.13

RUN mkdir /app
WORKDIR /app
COPY . .
RUN pip install .

CMD ics_caldav_sync
