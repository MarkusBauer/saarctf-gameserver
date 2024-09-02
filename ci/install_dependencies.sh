#!/usr/bin/env bash
set -euxo pipefail

# Install deb dependencies
apt-get update
apt-get install -y \
    curl
#curl -sL https://deb.nodesource.com/setup_12.x | bash
apt-get -y install --no-install-recommends \
    build-essential \
    clang \
    cmake \
    g++ \
    git \
    iputils-ping \
    libev-dev \
    libhiredis-dev \
    libpq-dev \
    libssl-dev \
    nodejs \
    postgresql-client-15 \
    postgresql-server-dev-all \
    psmisc \
    python3 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-venv \
    python3-wheel \
    python3-cryptography \
    python3-redis python3-psycopg2 \
    nodejs npm

ln -s /usr/bin/nodejs /usr/local/bin/node

# Install pip dependencies
make deps deps-script

# Install npm dependencies
npm install
npm run build
# Install and build the scoreboard
pushd scoreboard
npm install
npm run build
popd
