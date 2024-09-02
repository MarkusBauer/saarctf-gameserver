#!/usr/bin/env bash

# Called as "up" script from OpenVPN - set device options and mark team as "online" for the gameserver

set -e

cd "$( dirname "${BASH_SOURCE[0]}" )"
# Load bpf program on interface
bpf/install.sh "$1"
# Install rate-limiting queue on interface
ratelimit/install.sh "$1"
