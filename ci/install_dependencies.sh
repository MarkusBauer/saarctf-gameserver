#!/usr/bin/env bash
set -euxo pipefail

# Install deb dependencies
apt-get update
apt-get install -y \
    curl
curl -sL https://deb.nodesource.com/setup_12.x | bash
apt-get -y install --no-install-recommends \
    clang-7 \
    cmake \
    g++ \
    git \
    libev-dev \
    libhiredis-dev \
    libpq-dev \
    libssl-dev \
    nodejs \
    postgresql-client-10 \
    postgresql-server-dev-all \
    psmisc \
    python2.7 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-wheel

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
