#!/usr/bin/env bash

# Called as "down" script from OpenVPN - set device options and mark team as "offline" for the gameserver
# $1 = team ID or "teamXY" or "teamXY-vulnbox"
# $2 = "teamhosted" or not present

set -e

source /etc/profile.d/env.sh 2>/dev/null || true

cd "$( dirname "${BASH_SOURCE[0]}" )"
# Mark in database as disconnected
./on-disconnect.py "$1" "$2"

TEAMID=$(echo "$1" | sed 's/[^0-9]*//g')
if [ "$2" = "teamhosted" ]; then
  systemctl start "vpn2@team$TEAMID-cloud" || true
fi
if [ "$2" = "cloudhosted" ]; then
  systemctl start "vpn@team$TEAMID" || true
fi
