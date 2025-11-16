import os
import shutil
import struct
import subprocess
from pathlib import Path

EASYRSA_BINARY = '/usr/share/easy-rsa/easyrsa'
REUSE_DH = True


def read(fname: str | Path) -> str:
    with open(fname, 'r') as f:
        return f.read()


def write(fname: str | Path, content: str) -> None:
    with open(fname, 'w') as f:
        f.write(content)


def readb(fname: str | Path) -> bytes:
    with open(fname, 'rb') as f:
        return f.read()


def writeb(fname: str | Path, content: bytes) -> None:
    with open(fname, 'wb') as f:
        f.write(content)


def network_to_mask(network: str) -> str:
    """
    "1.2.3.4/16" => "1.2.3.4 255.255.0.0"
    :param network:
    :return:
    """
    ip, netrange = network.split('/')
    mask_int = int('1' * int(netrange) + '0' * (32 - int(netrange)), 2)
    mask = str(mask_int >> 24) + '.' + str((mask_int >> 16) & 0xff) + '.' + str((mask_int >> 8) & 0xff) + '.' + str(
        mask_int & 0xff)
    return ip + ' ' + mask


def generate_vpn_keys(directory: Path) -> None:
    path = directory / 'pki'
    if (path / 'ta.key').exists():
        print('[.] VPN keys already present')
        return
    env = dict(os.environ.items())
    env['EASYRSA_BATCH'] = '1'
    subprocess.check_call([EASYRSA_BINARY, 'init-pki'], env=env, cwd=directory)
    subprocess.check_call([EASYRSA_BINARY, 'build-ca', 'nopass'], env=env, cwd=directory)
    subprocess.check_call([EASYRSA_BINARY, 'gen-req', 'server', 'nopass'], env=env, cwd=directory)
    subprocess.check_call([EASYRSA_BINARY, 'gen-req', 'TeamMember', 'nopass'], env=env, cwd=directory)
    subprocess.check_call([EASYRSA_BINARY, 'sign-req', 'server', 'server'], env=env, cwd=directory)
    subprocess.check_call([EASYRSA_BINARY, 'sign-req', 'client', 'TeamMember'], env=env, cwd=directory)
    if REUSE_DH and os.path.exists('/tmp/dh.pem'):
        shutil.copy('/tmp/dh.pem', os.path.join(path, 'dh.pem'))
    else:
        subprocess.check_call([EASYRSA_BINARY, 'gen-dh'], env=env, cwd=directory)
        if REUSE_DH:
            shutil.copy(os.path.join(path, 'dh.pem'), '/tmp/dh.pem')
    subprocess.check_call(['openvpn', '--genkey', '--secret', 'ta.key'], cwd=path)
    print('[*] VPN keys have been generated.')


def generate_additional_vpn_keys(directory: str, name: str) -> None:
    path = os.path.join(directory, 'pki')
    if os.path.exists(os.path.join(path, 'issued', f'{name}.crt')):
        return
    env = dict(os.environ.items())
    env['EASYRSA_BATCH'] = '1'
    subprocess.check_call([EASYRSA_BINARY, 'gen-req', name, 'nopass'], env=env, cwd=directory)
    subprocess.check_call([EASYRSA_BINARY, 'sign-req', 'client', name], env=env, cwd=directory)


def format_vpn_keys(directory: Path) -> str:
    included_files = {
        'ca': directory / 'pki' / 'ca.crt',
        'cert': directory / 'pki' / 'issued' / 'TeamMember.crt',
        'key': directory / 'pki' / 'private' / 'TeamMember.key',
        'tls-auth': directory / 'pki' / 'ta.key'
    }
    config = ''
    for name, fname in included_files.items():
        config += f'\n<{name}>\n'
        config += read(fname)
        config += f'\n</{name}>\n'
    return config


def format_vpn_server_keys(directory: Path) -> str:
    included_files = {
        'ca': directory / 'pki' / 'ca.crt',
        'cert': directory / 'pki' / 'issued' / 'server.crt',
        'key': directory / 'pki' / 'private' / 'server.key',
        'dh': directory / 'pki' / 'dh.pem',
        'tls-auth': directory / 'pki' / 'ta.key',
    }
    config = ''
    for name, fname in included_files.items():
        config += f'\n<{name}>\n'
        config += read(fname)
        config += f'\n</{name}>\n'
    return config


def gen_wg_keypair() -> tuple[str, str]:
    privkey = subprocess.check_output(['wg', 'genkey']).decode('utf-8').strip()
    pubkey = subprocess.check_output(['wg', 'pubkey'], input=privkey.encode()).decode('utf-8').strip()
    return privkey, pubkey
