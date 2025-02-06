#!/usr/bin/env bash
set -eu

# ARGUMENT 1: "game" or "team"
# to dump team<->game or team<->team traffic
# ARGUMENT 2: service ID (for "team" only)


if [[ "$1" == "game" ]]; then
	interface="nflog:5"
	filename_scheme="traffic_game_%Y-%m-%d_%H_%M_%S.pcap"
elif [[ "$1" == "team" ]]; then
	interface="nflog:$((10+$2))"
	filename_scheme="traffic_team_%Y-%m-%d_%H_%M_%S_svc$(printf "%02d" $2).pcap"
else
	echo 'Error: Argument must be either "game" or "team".' >&2
	exit 1
fi


DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# TODO configure?
if [ -d "/tmp/temptraffic/" ]; then
  FOLDER="/tmp/temptraffic"
else
  FOLDER="/tmp"
fi

exec tcpdump -i "$interface" -s0 \
    -B 131072 \
    -G 60 -w "$FOLDER/$filename_scheme" \
    -z "$DIR/move-${1}traffic.sh" -Z nobody
