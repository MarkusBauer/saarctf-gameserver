#!/bin/bash

# Requirements:
# pip install --upgrade -r requirements-dev.txt

exec mypy --config-file mypy.ini --no-incremental controlserver/*.py scripts/*.py checker_runner/*.py gamelib/*.py vpn/*.py vpnboard/*.py
