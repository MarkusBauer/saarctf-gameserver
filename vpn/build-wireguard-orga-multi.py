#!/usr/bin/env python3
import os
import sys
from pathlib import Path

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from saarctf_commons.config import config, load_default_config

from vpn.vpnlib import gen_wg_keypair


def configure_wireguard_vpnserver(orga_dir: Path) -> None:
    server_sk, server_pk = gen_wg_keypair()
    server_ip = config.NETWORK.team_id_to_gateway_ip(0)
    server_ip_base = ".".join(server_ip.split(".")[:-1])
    server_config = f"""
[Interface]
Address = {server_ip}/24
SaveConfig = true
ListenPort = 51821
PrivateKey = {server_sk}
"""

    for i in range(10, 64):
        client_sk, client_pk = gen_wg_keypair()
        server_config += f"""[Peer]
PublicKey = {client_pk}
AllowedIPs = {server_ip_base}.{i}/32
"""
        client_config = f"""
[Interface]
PrivateKey = {client_sk}
Address = {server_ip_base}.{i}/32

[Peer]
PublicKey = {server_pk}
AllowedIPs = 10.32.0.0/15
Endpoint = {config.CONFIG["network"]["vpn_host"]}:51821
PersistentKeepalive = 20
"""
        (orga_dir / f"client-{i:02d}.conf").write_text(client_config)

    (orga_dir / "orga.conf").write_text(server_config)


if __name__ == "__main__":
    load_default_config()

    orga_dir = config.VPN_BASE_DIR / "orga"
    orga_dir.mkdir(exist_ok=True, parents=True)

    configure_wireguard_vpnserver(orga_dir)
    print("Configurations generated:")
    print(f'  server: {orga_dir / "orga.conf"}')
    print(f'  client: {orga_dir / "client-XY.conf"}')
    print(f"Installation: ln -s {orga_dir}/orga.conf /etc/wireguard/")
    print(
        "Activation:   systemctl start wg-quick@orga && systemctl enable wg-quick@orga"
    )
