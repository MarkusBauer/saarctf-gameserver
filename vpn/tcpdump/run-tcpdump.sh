#!/usr/bin/env bash
set -e

# ARGUMENT 1: "game" or "team"
# to dump team<->game or team<->team traffic


if [[ "$1" == "game" ]]; then
	interface="nflog:5"
else
	if [[ "$1" == "team" ]]; then
		interface="nflog:6"
	else
		echo 'Error: Argument must be either "game" or "team".' >&2
		exit 1
	fi
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
    -G 60 -w "$FOLDER/traffic_$1_%Y-%m-%d_%H_%M_%S.pcap" \
    -z "$DIR/move-${1}traffic.sh" -Z nobody
