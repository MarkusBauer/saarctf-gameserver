#!/bin/bash
#set -eux
set -eu

# Argument 1: Team ID
# Defined by OpenVPN: $dev

NEW_CONN_RATE=100mbit    # guaranteed bandwidth
NEW_CONN_RATE_MAX=1gbit  # maximum bandwidth (if spare bandwidth is available)
REPLY_RATE=20mbit        # guaranteed bandwidth
REPLY_RATE_MAX=50mbit    # max bandwidth (if spare bandwidth is available)

NEW_CONN_MARK=0x100000
REPLY_MARK=0x200000
# ensure that these marks are set correctly with iptables, e.g.
# iptables -t mangle -A FORWARD -m conntrack --ctdir ORIGINAL -j MARK --set-mark ${NEW_CONN_MARK}
# iptables -t mangle -A FORWARD -m conntrack --ctdir REPLY -j MARK --set-mark ${REPLY_MARK}

# delete old qdisc
sudo tc qdisc del dev ${dev} root || true

# create prio with 2 classes as root,
# set priomap to map everything to class 1 by default
sudo tc qdisc add dev ${dev} root handle 1: prio bands 2 priomap 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0 0
# filter marked traffic to class :2
sudo tc filter add dev ${dev} parent 1: basic match "meta(nf_mark mask 0x300000 eq ${NEW_CONN_MARK})" flowid 1:2
sudo tc filter add dev ${dev} parent 1: basic match "meta(nf_mark mask 0x300000 eq ${REPLY_MARK})" flowid 1:2

# create sfq for important traffic
sudo tc qdisc add dev ${dev} parent 1:1 handle 10: sfq

# create htb for marked traffic
sudo tc qdisc add dev ${dev} parent 1:2 handle 20: htb default 1

# add subclasses for new connections and replies
sudo tc class add dev ${dev} parent 20: classid 20:1 htb rate ${NEW_CONN_RATE} ceil ${NEW_CONN_RATE_MAX}
sudo tc class add dev ${dev} parent 20: classid 20:2 htb rate ${REPLY_RATE} ceil ${REPLY_RATE_MAX}

# and filter marked traffic to it
sudo tc filter add dev ${dev} parent 20: basic match "meta(nf_mark mask 0x300000 eq ${NEW_CONN_MARK})" flowid 20:1
sudo tc filter add dev ${dev} parent 20: basic match "meta(nf_mark mask 0x300000 eq ${REPLY_MARK})" flowid 20:2

# create sfq for both
sudo tc qdisc add dev ${dev} parent 20:1 handle 21: sfq
sudo tc qdisc add dev ${dev} parent 20:2 handle 22: sfq
