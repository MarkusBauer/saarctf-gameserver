#!/usr/bin/env bash

# Called as "up" script from OpenVPN - set device options and mark team as "online" for the gameserver
# $1 = team ID
# $2 = "teamhosted" or not present

set -e

source /etc/profile.d/env.sh 2>/dev/null || true

cd "$( dirname "${BASH_SOURCE[0]}" )"
# Load bpf program on interface
bpf/install.sh "$1"
# Install rate-limiting queue on interface
ratelimit/install.sh "$1"
# Mark in database as connected
./on-connect.py "$1" "$2"

if [ "$2" = "teamhosted" ]; then
  systemctl stop "vpn2@team$1-cloud"
fi

# Possibly prevent some bugs. When people start a cloud VM, we get a connection to vulnbox-VPN, which should enable cloud-vpn and disable team-hosted vpn
if [ "$2" = "cloudhosted" ]; then
  systemctl stop "vpn@team$1"
  systemctl start "vpn2@team$1-cloud" || true
fi
