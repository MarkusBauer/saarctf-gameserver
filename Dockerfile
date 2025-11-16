FROM node:22 AS scoreboard_build

RUN mkdir /opt/scoreboard /opt/controlserver
WORKDIR /opt/scoreboard

ADD scoreboard/package.json scoreboard/package-lock.json /opt/scoreboard/
RUN --mount=type=cache,target=/root/.npm \
     npm install

ADD scoreboard /opt/scoreboard
ADD controlserver/static /opt/controlserver/static
# TODO find a way to set this dynamically?
ENV SAARCTF_ENVIRONMENT=None
RUN npm run build


FROM node:22 AS frontend_build
WORKDIR /opt
ADD package.json /opt/
RUN --mount=type=cache,target=/root/.npm \
     npm install

ADD controlserver/static /opt/controlserver/static
# TODO find a way to set this dynamically?
ENV SAARCTF_ENVIRONMENT=None
RUN npm run build


# the actual container with all python-based things
FROM python:3.13
WORKDIR /opt

ADD requirements* /opt/
ADD Makefile /opt/
ADD gamelib /opt/gamelib

RUN --mount=type=cache,target=/root/.cache \
    make deps && \
    . venv/bin/activate && \
    pip install gunicorn && \
    mkdir -p scoreboard

ADD alembic.ini /opt/alembic.ini
ADD checker_runner /opt/checker_runner
ADD controlserver /opt/controlserver
ADD migrations /opt/migrations
ADD run.sh /opt/run.sh
ADD saarctf_commons /opt/saarctf_commons
ADD sample_files /opt/sample_files
ADD scripts /opt/scripts
ADD vpn /opt/vpn
ADD vpnboard /opt/vpnboard
ADD wireguard-sync /opt/wireguard-sync

COPY --from=scoreboard_build /opt/scoreboard/dist /opt/scoreboard/dist
COPY --from=frontend_build /opt/controlserver/static /opt/controlserver/static

ENV FLASK_APP=controlserver/app.py
STOPSIGNAL SIGINT

ENTRYPOINT ["/opt/venv/bin/python"]
