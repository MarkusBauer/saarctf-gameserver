#!/usr/bin/env bash
set -euxo pipefail

# Install deb dependencies
apt-get update
apt-get install -y \
    curl
#curl -sL https://deb.nodesource.com/setup_12.x | bash
apt-get -y install --no-install-recommends \
    clang-11 \
    cmake \
    g++ \
    git \
    libev-dev \
    libhiredis-dev \
    libpq-dev \
    libssl-dev \
    nodejs \
    postgresql-client-13 \
    postgresql-server-dev-all \
    psmisc \
    python2.7 \
    python3 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel \
    python3-cryptography \
    python3-redis python3-psycopg2 \
    python3-flask python3-flask-api python3-flask-migrate python3-flask-restful \
    python3-sqlalchemy \
    python3-setproctitle python3-filelock python3-htmlmin python3-ujson \
    nodejs npm

ln -s /usr/bin/nodejs /usr/local/bin/node

# Install pip dependencies
python3 -m pip install -r requirements.txt
python3 -m pip install -r requirements-script.txt
python3 -m pip install -r requirements-dev.txt

# Install npm dependencies
npm install
npm run build
# Install and build the scoreboard
pushd scoreboard
npm install
npm run build
popd
