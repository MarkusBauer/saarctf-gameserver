#!/bin/bash
#set -eux
set -eu

# Argument 1: Team ID
# Defined by OpenVPN: $dev

NEW_CONN_RATE=100mbit    # guaranteed bandwidth
NEW_CONN_RATE_MAX=500mbit  # maximum bandwidth (if spare bandwidth is available)
REPLY_RATE=20mbit        # guaranteed bandwidth
REPLY_RATE_MAX=50mbit    # max bandwidth (if spare bandwidth is available)

NEW_CONN_MARK=0x100000
REPLY_MARK=0x200000
# ensure that these marks are set correctly with iptables, e.g.
# iptables -t mangle -A FORWARD -m conntrack --ctdir ORIGINAL -j MARK --set-mark ${NEW_CONN_MARK}
# iptables -t mangle -A FORWARD -m conntrack --ctdir REPLY -j MARK --set-mark ${REPLY_MARK}

# delete old qdisc
sudo tc qdisc del dev ${dev} root 2>/dev/null || true

# objective: Always prioritize gameserver traffic vs contestant traffic
# create prio with 2 classes (bands) as root
# prio will always send packets queued in a lower band before sending packets from higher bands
# set priomap to map everything to class 1 (==band 0) by default, this effectively ignores any TOS bits in IP headers
sudo tc qdisc add dev ${dev} root handle 1: prio bands 2 priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0

# filter marked traffic (==contestant traffic) into class :2
# any traffic from teams will be marked by our firewall
sudo tc filter add dev ${dev} parent 1: basic match "meta(nf_mark mask 0x300000 eq ${NEW_CONN_MARK})" flowid 1:2
sudo tc filter add dev ${dev} parent 1: basic match "meta(nf_mark mask 0x300000 eq ${REPLY_MARK})" flowid 1:2

# objective: Fairly multiplex among connections with gameserver
# create sfq for important traffic
sudo tc qdisc add dev ${dev} parent 1:1 handle 10: sfq

# create htb for traffic among contestants, by default, packets are considered attack / inbound
sudo tc qdisc add dev ${dev} parent 1:2 handle 20: htb default 1

# objective: awr separate limits at which attackers can send packets and receive replies
# add subclasses for inbound / attack vs. reply vs internal traffic
sudo tc class add dev ${dev} parent 20: classid 20:1 htb rate ${NEW_CONN_RATE} ceil ${NEW_CONN_RATE_MAX}
sudo tc class add dev ${dev} parent 20: classid 20:2 htb rate ${REPLY_RATE} ceil ${REPLY_RATE_MAX}
sudo tc class add dev ${dev} parent 20: classid 20:3 htb rate 5mbit ceil 100mbit

# filter attack vs. reply vs internal traffic to respective HTB classes
sudo tc filter add dev ${dev} parent 20: prio 2 basic match "meta(nf_mark mask 0x300000 eq ${NEW_CONN_MARK})" flowid 20:1
sudo tc filter add dev ${dev} parent 20: prio 3 basic match "meta(nf_mark mask 0x300000 eq ${REPLY_MARK})" flowid 20:2
sudo tc filter add dev ${dev} parent 20: prio 1 basic match "meta(nf_mark mask 0x0c00 eq 0x0800)" flowid 20:3

# Within attack vs. reply vs. internal: Fairly distribute bandwidth among connections
sudo tc qdisc add dev ${dev} parent 20:1 handle 21: sfq
sudo tc qdisc add dev ${dev} parent 20:2 handle 22: sfq
# Ensure that players "feel" the throttle in the network even when there isn't much load
sudo tc qdisc add dev ${dev} parent 20:3 handle 23: sfq # tbf rate 5mbit burst 300mb latency 60 peakrate 100mbit mtu 300mb
