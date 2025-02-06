#!/bin/bash

set -e

# DIR = "vpn" directory, ROOT = saarctf repo root
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
ROOT="$(dirname "$DIR")"

GAMESERVER_IP=`"$ROOT/run.sh" "$ROOT/saarctf_commons/config.py" get network gameserver_ip`
GAMENETWORK_RANGE=`"$ROOT/run.sh" "$ROOT/saarctf_commons/config.py" get network game`

# cleanup
iptables -F FORWARD
iptables -F INPUT



# NAT / ANONYMIZE
iptables -t nat -F POSTROUTING
iptables -t nat -A POSTROUTING -o tun+ -j MASQUERADE --random -m comment --comment "Nat for all"
iptables -t nat -A POSTROUTING -o orga+ -j MASQUERADE --random -m comment --comment "Nat for all"
iptables -t nat -A POSTROUTING -o tun+ -p tcp --syn -j TCPMSS --clamp-mss-to-pmtu -m comment --comment "Fix MSS"  # thanks to Sebastian Neef
iptables -t mangle -F PREROUTING
iptables -t mangle -F FORWARD




# Chain to handle accepted network traffic (includes logs etc)
iptables -N vpn-ok || true
iptables -F vpn-ok
iptables -A vpn-ok
# "Log" forwarded connections (make accessible for tcpdump) / excluding SSH (TCP 22) from team2team traffic
iptables -A vpn-ok   -i tun+ ! -o tun+ -j NFLOG --nflog-group 5 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->game traffic (1/2)"
iptables -A vpn-ok ! -i tun+   -o tun+ -j NFLOG --nflog-group 5 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->game traffic (2/2)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0x0000/0xf000 -j NFLOG --nflog-group 10 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 0)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0x1000/0xf000 -j NFLOG --nflog-group 11 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 1)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0x2000/0xf000 -j NFLOG --nflog-group 12 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 2)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0x3000/0xf000 -j NFLOG --nflog-group 13 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 3)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0x4000/0xf000 -j NFLOG --nflog-group 14 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 4)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0x5000/0xf000 -j NFLOG --nflog-group 15 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 5)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0x6000/0xf000 -j NFLOG --nflog-group 16 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 6)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0x7000/0xf000 -j NFLOG --nflog-group 17 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 7)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0x8000/0xf000 -j NFLOG --nflog-group 18 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 8)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0x9000/0xf000 -j NFLOG --nflog-group 19 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 9)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0xa000/0xf000 -j NFLOG --nflog-group 20 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 10)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0xb000/0xf000 -j NFLOG --nflog-group 21 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 11)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0xc000/0xf000 -j NFLOG --nflog-group 22 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 12)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0xd000/0xf000 -j NFLOG --nflog-group 23 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 13)"
iptables -A vpn-ok   -i tun+   -o tun+ -m mark --mark 0xe000/0xf000 -j NFLOG --nflog-group 24 --nflog-threshold 16 -m comment --comment "tcpdump interface for team<->team traffic (service 14)"
# service 15 = SSH, we don't log that
# finally pass traffic
iptables -A vpn-ok -j ACCEPT



# Chain to block network / teams
# this chain is later filled with rules to disable network access / block a single team.
iptables -N vpn-blocking || true
iptables -F vpn-blocking
iptables -A vpn-blocking -j REJECT  # block by default, until iptables management script has been started / restarted



# FORWARD CHAIN
# 0. User-defined input
iptables -N vpn-user || true
iptables -A FORWARD -i tun+ -j vpn-user -m comment --comment "Temporary user-defined rules"
iptables -A FORWARD -i orga+ -j vpn-user -m comment --comment "Temporary user-defined rules"
# 1. Forwarding that is allowed regardless of blocking state (and not logged):
iptables -A FORWARD -i tun+ -d $GAMESERVER_IP -p icmp -j ACCEPT -m comment --comment "Gameserver/ping"
iptables -A FORWARD -o tun+ -s $GAMESERVER_IP -p icmp -j ACCEPT -m comment --comment "Gameserver/ping"
iptables -A FORWARD -i tun+ -d $GAMESERVER_IP -p tcp --dport 31337 -j vpn-ok -m comment --comment "Gameserver/Submitter"
iptables -A FORWARD -o tun+ -s $GAMESERVER_IP -p tcp --sport 31337 -j vpn-ok -m comment --comment "Gameserver/Submitter"
iptables -A FORWARD -i orga+ -j vpn-ok -m comment --comment "Orga can connect anywhere"
iptables -A FORWARD -o orga+ -m conntrack --ctstate RELATED,ESTABLISHED -j vpn-ok -m comment --comment "Responses to orga"
# 2. Check if network is disabled
iptables -A FORWARD -i tun+ -j vpn-blocking
iptables -A FORWARD ! -i tun+ -o tun+ -j vpn-blocking
# 3. Allow VPN connections to the game server, but not the rest of the internal network
iptables -A FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j vpn-ok
iptables -A FORWARD -i tun+ -o tun+ -j vpn-ok -m comment --comment "Team to Team"
iptables -A FORWARD -i tun+ ! -o tun+ -j DROP -m comment --comment "VPN => internal network"

# RATE LIMIT
# (actual limit is enforced by tc, we just mark packets accordingly)
NEW_CONN_MARK=0x100000/0x300000
REPLY_MARK=0x200000/0x300000
iptables -t mangle -A PREROUTING -i tun+ -m conntrack --ctdir ORIGINAL -j MARK --set-mark ${NEW_CONN_MARK} -m comment --comment "Mark team to team attack traffic as ${NEW_CONN_MARK}"
iptables -t mangle -A PREROUTING -i tun+ -m conntrack --ctdir REPLY -j MARK --set-mark ${REPLY_MARK} -m comment --comment "Mark team to team response traffic as ${REPLY_MARK}"
# KEEP CT MARKS
iptables -t mangle -A PREROUTING -m state --state NEW -j CONNMARK --save-mark --mask 0xfc00
iptables -t mangle -A PREROUTING -m state --state ESTABLISHED,RELATED -j CONNMARK --restore-mark --mask 0xfc00


# INPUT CHAIN - Filter connections from VPN to this machine
iptables -A INPUT -i ens10 -j ACCEPT
iptables -A INPUT -i enp7s0 -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT
iptables -A INPUT -i tun+ -p icmp -j ACCEPT -m comment --comment "Ping to VPN gateway"
iptables -A INPUT -i tun+ -p udp --dport 123 -j ACCEPT -m comment --comment "NTP on VPN gateway"
iptables -A INPUT -i tun+ -p tcp --dport 62015 -j ACCEPT -m comment --comment "Port for some service-related backends"
iptables -A INPUT -i tun+ -j DROP
iptables -A INPUT -p tcp --dport 22 -j ACCEPT -m comment --comment "SSH"
iptables -A INPUT -p tcp --dport 80 -j ACCEPT -m comment --comment "HTTP / VPN-Board"
iptables -A INPUT -p tcp --dport 443 -j ACCEPT -m comment --comment "HTTPS / VPN-Board"
# iptables -A INPUT -p udp --dport 443 -j ACCEPT -m comment --comment "HTTPS / VPN-Board (http3/quic)"
iptables -A INPUT -p udp -j ACCEPT -m comment --comment "OpenVPN/WireGuard servers"
iptables -P INPUT DROP

# Filter connections from outside world to VPN - TODO IPs
iptables -A FORWARD -o tun+ -s 10.32.250.0/24 -j vpn-ok -m comment --comment "Gameserver to VPN"
iptables -N outside-to-vpn || iptables -F outside-to-vpn
iptables -A FORWARD -o tun+ ! -i tun+ -j outside-to-vpn -m comment --comment "Outside world -> VPN (1)"
iptables -A outside-to-vpn -o tun+ ! -i orga+ -j DROP -m comment --comment "Outside world -> VPN (2)"

# Disable conntrack for traffic from the outer world. Thus, UDP floods won't fill/crash conntrack.
# This requires manually allowing incoming UDP packets, because "related" won't do it anymore.
# Luckily we have "-p udp -j ACCEPT" in the INPUT rules already.
# TODO not really tested
iptables -t raw -A PREROUTING -p udp -i eth0 -j NOTRACK
iptables -t raw -A PREROUTING -p udp -i ens1 -j NOTRACK
iptables -t raw -A PREROUTING -p icmp -i eth0 -j NOTRACK
iptables -t raw -A PREROUTING -p icmp -i ens1 -j NOTRACK



# Check kernel JIT
echo "Kernel JIT status:"
cat /proc/sys/net/core/bpf_jit_enable || true

# enable IPv4 forward
echo "Enable IPv4 forwarding ..."
sysctl net.ipv4.ip_forward
sysctl -w net.ipv4.ip_forward=1
sysctl net.ipv4.ip_forward


# default route to avoid loops
# TODO hardcoded for now
#ip route add blackhole "$GAMENETWORK_RANGE" || true
ip route add blackhole "10.32.0.0/17" || true
ip route add blackhole "10.32.128.0/18" || true
ip route add blackhole "10.32.192.0/19" || true
ip route add blackhole "10.33.0.0/16" || true
ip route add blackhole "10.34.0.0/16" || true
ip route add blackhole "10.35.0.0/16" || true


echo "===== IPTABLES SET ====="
iptables -S
iptables -t nat -S
echo "========================"

echo "If 'manage-iptables.py' is running, please restart now!"
