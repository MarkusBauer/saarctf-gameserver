#!/usr/bin/env bash

# Run manually on the internal interface(s)
# Argument 1: Interface (default: autodetect)

set -eu

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

# find interface
if [ $# -eq 0 ]; then
	dev=$(ip -o -4 addr show | grep 10.32.250.1 | grep -oP '\d+:\s+\K\w+')
	if [ -z "$dev" ]; then
		echo "No interface given/found"
		exit 1
	fi
else
	dev=$1
fi

tc qdisc del dev $dev clsact 2>/dev/null || true
tc qdisc add dev $dev clsact
tc filter del dev $dev ingress
tc filter add dev $dev ingress bpf object-file "${DIR}/traffic_stats_gameserver.o" sec traffic_stats_gameserver_ingress direct-action
echo "Added gameserver bpf to interface $dev"
