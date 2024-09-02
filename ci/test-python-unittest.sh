#!/usr/bin/env bash
set -euxo pipefail

# Run static checker
make check

# Configure database credentials for container setup
sed 's/"database": "saarctf"/"database": "saarctf_unittest"/' ./config.containers.json > ./config.test.json
export PGPASSWORD=123456789
echo 'CREATE DATABASE saarctf_unittest;' | psql -Usaarsec -h postgres saarctf

make test
