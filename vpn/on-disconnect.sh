#!/usr/bin/env bash

# Called as "down" script from OpenVPN - set device options and mark team as "offline" for the gameserver

set -e

source /etc/profile.d/env.sh 2>/dev/null || true

cd "$( dirname "${BASH_SOURCE[0]}" )"
# Mark in database as disconnected
./on-disconnect.py "$1"
