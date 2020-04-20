#!/usr/bin/env bash
set -euxo pipefail

# Run static checker
./run-mypy.sh  # || echo "WARNING: STATIC TYPECHECKER FAILED. IGNORED FOR NOW."

# Configure database credentials for container setup
sed 's/"database": "saarctf"/"database": "saarctf_unittest"/' ./config.containers.json > ./config.test.json
export PGPASSWORD=123456789
echo 'CREATE DATABASE saarctf_unittest;' | psql -Usaarsec -h postgres saarctf
python3 -m unittest tests/test_*.py
