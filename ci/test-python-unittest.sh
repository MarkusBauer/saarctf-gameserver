#!/usr/bin/env bash
set -euxo pipefail

# Run static checker
make check

# Configure database credentials for container setup
sed 's/"database": "saarctf"/"database": "saarctf_unittest"/' ./ci-config.yaml > ./config.test.yaml
export PGPASSWORD=123456789
echo 'CREATE DATABASE saarctf_unittest;' | psql -Usaarsec -h postgres saarctf

make test
