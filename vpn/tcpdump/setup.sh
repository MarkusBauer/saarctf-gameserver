#!/usr/bin/env bash

# Run this script once before starting tcpdump, to create all folders

set -e

# TODO configurable?
mkdir -p /tmp
mkdir -p /tmp/teamtraffic
mkdir -p /tmp/gametraffic
chown nobody:nogroup /tmp/teamtraffic
chown nobody:nogroup /tmp/gametraffic
