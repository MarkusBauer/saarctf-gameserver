#!/bin/bash

set -e

# tc qdisc del dev eth0 clsact
tc filter del dev $dev egress
tc filter del dev $dev ingress
tc filter show dev $dev egress
tc filter show dev $dev ingress
