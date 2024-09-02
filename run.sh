#!/usr/bin/env bash
set -e

cd "`dirname "$0"`"

# make --silent deps

. venv/bin/activate
exec venv/bin/python3 "$@"
