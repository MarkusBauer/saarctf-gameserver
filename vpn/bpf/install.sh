#!/usr/bin/env bash

# Argument 1: Team ID
# Defined by OpenVPN: $dev

set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

tc qdisc del dev $dev clsact 2>/dev/null || true
tc qdisc add dev $dev clsact

tc filter del dev $dev egress
tc filter del dev $dev ingress
tc filter add dev $dev egress  bpf object-file "${DIR}/anonymize_traffic.o" sec anonymize_traffic direct-action
# tc filter add dev $dev ingress bpf object-file "${DIR}/anonymize_traffic.o" sec anonymize_traffic direct-action
tc filter add dev $dev egress  bpf object-file "${DIR}/traffic_stats.o" sec traffic_stats_egress direct-action
tc filter add dev $dev ingress bpf object-file "${DIR}/traffic_stats.o" sec traffic_stats_ingress direct-action
