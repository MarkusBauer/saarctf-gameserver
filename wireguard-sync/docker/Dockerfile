FROM python:3.12-alpine3.20 AS poetry

RUN apk add py3-virtualenv
WORKDIR /opt/poetry
RUN python3 -m venv venv
ENV VIRTUAL_ENV=/opt/poetry/venv
ENV PATH=$VIRTUAL_ENV/bin:$PATH
RUN pip install poetry

FROM python:3.12-alpine3.20

RUN apk add wireguard-tools iproute2

COPY --from=poetry /opt/poetry/venv /opt/poetry/venv
RUN ln -s /opt/poetry/venv/bin/poetry /bin/poetry

WORKDIR /opt/saarctf/
RUN python3 -m venv ./venv
ENV VIRTUAL_ENV=/opt/saarctf/venv
ENV PATH=$VIRTUAL_ENV/bin:$PATH

WORKDIR /opt/saarctf/router
COPY pyproject.toml .
COPY poetry.lock .

RUN poetry install --with dev --no-root --compile
COPY wireguard_sync wireguard_sync
RUN poetry install
