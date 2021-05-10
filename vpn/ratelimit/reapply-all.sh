#!/usr/bin/env bash

set -e

INTERFACES=$(ip -o link show | awk -F': ' '{print $2}' | grep tun)

for i in $INTERFACES; do
	echo "- Apply rates on $i ..."
	dev=$i ./install.sh
done

echo "[DONE!]"
