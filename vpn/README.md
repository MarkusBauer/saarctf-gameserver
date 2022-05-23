Network architecture
====================

General architecture
--------------------
`python3 build-openvpn-config-oneperteam.py` and `python3 build-openvpn-config-cloud.py` create all necessary config files (in `$SAARCTF_CONFIG_DIR/vpn`):
- `config-server/*.conf` : OpenVPN server configurations (including cloudhosting config: `-cloud` and `-vulnbox`)
- `config-client/*.conf` : OpenVPN client configurations to be sent to the teams
- `secrets/...` : Secrets shared with the teams. Should be cached to not invalidate team's config.

### Network structure
All IP ranges are subject to change. 

- Game network: `10.32.0.0/15`
- VPN gateway: `10.32.250.1`
- Internal machines: `10.32.250.0/24`
- Teams: `10.32.X.0/24`

The VPN gateway is the central routing server. All teams connect via OpenVPN P2P connection. 
The team's VPN has `10.48.X.1/30`, which is not publicly routable.

`10.32.0.1 = 10.48.X.1   <--- (vpn) --->   10.48.X.2 = 10.32.X.1 (team's gateway)`

On the VPN server, every team with ID `X` is connected by a dedicated OpenVPN instance with interface `tunX`. 

- IPTables cares about forwarding traffic and NAT (masquerade). Origin (viewed from teams) is their VPN partner: `10.48.X.1`
- We attach a BPF traffic anonymizer to the egress of each `tunX` interface
- We attack a BPF traffic counter to each `tunX` interface
- Separation between team / game traffic is based entirely on interfaces.
- All packets from teams are marked with `1<<16 | team_id`
- All traffic is forwarded to nflog (group 5: game, group 6: team) for tcpdump


### Routes
- Servers => VPN-Host: `10.32.0.0/16`
- Teams => VPN-Host: `10.32.0.0/16`
- Teams => intern: `10.32.X.0/24`
- VPN-Host => Servers: `10.32.0.0/24`
- VPN-Host => Teams: `10.32.X.0/24`
- VPN-Host => blackhole: `10.32.0.0/16` (offline teams)

VPN-internal traffic `10.48.0.0/16` is publicly not routable. 




Features
--------
- NAT with additional anonymity (TTL)
- VPN connection state is logged to database (table `teams` columns `vpn_connected` for selfhosted and `vpn2_connected` for cloudhosted-vulnbox)
- VPN status board available with the scoreboard
- Firewall can be controlled over Dashboard / Redis (open/close/ban/unban)
- Generates pcaps of the game / team traffic
- Traffic statistics in database (to be used by the frontend)


Components that must run
------------------------
### IPTables setup
`vpn/iptables.sh` - run after boot. Includes `net.ipv4.ip_forward`. 

### OpenVPN servers
For each `.conf` in config-server:
 
`python3 vpn/on-disconnect.py && exec openvpn --config xyz.conf`
 
Apply systemd to restart if needed. Check if python scripts (on-connect/on-disconnect) can be executed first.

### IPTables script
Open/close VPN when game starts/ends, bans teams etc.

`python3 vpn/manage-iptables.py`

### Traffic stats script
Counts packets / bytes / connections per team-VPN and keeps track in the database.

`python3 vpn/manage-trafficstats.py`

### tcpdump
We capture pcaps from the game traffic, in two distinct folders. Run `vpn/tcpdump/run-tcpdump.sh` twice:
- Team <-> Game traffic (`vpn/tcpdump/run-tcpdump.sh game`)
- Team <-> Team traffic (`vpn/tcpdump/run-tcpdump.sh team`)

The target folder is configured in `vpn/tcpdump/move-*.sh`.

### (what does not need attention)
Marking teams as online/offline and the BPF programs are handled by OpenVPN - no action required. 
