#!/usr/bin/env bash
set -euxo pipefail

# Configure database credentials for container setup
cp ./config.containers.json ./config.json

# Install additional dependencies
python3 -m pip install -r requirements.txt
python3 -m pip install -r script-requirements.txt
npm install
npm run build

# Setup database schema
flask db upgrade
