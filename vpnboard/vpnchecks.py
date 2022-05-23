import re
import subprocess
from typing import Optional
import requests


USE_NPING_TIMEPINGS = True


def test_ping(ip: str) -> Optional[float]:
    """
    :param ip:
    :return: Average ping time in ms, None if unreachable / unreliable
    """
    try:
        result = subprocess.run(['ping', '-c', '3', ip], stdout=subprocess.PIPE, timeout=5, check=False)
        if result.returncode != 0:
            return None
        times = re.findall(r'time=([\d.]+) ms', result.stdout.decode())
        if len(times) != 3:
            return None
        return sum(float(x) for x in times) / len(times)
    except subprocess.TimeoutExpired:
        return None


def test_nping(ip: str) -> Optional[float]:
    """
    :param ip:
    :return: Average ping time in ms, None if unreachable / unreliable
    """
    try:
        cmd = ['nping', '--privileged', '--icmp', '-c', '3']
        if USE_NPING_TIMEPINGS:
            cmd += ['--icmp-type', 'time']
        result = subprocess.run(cmd + [ip], stdout=subprocess.PIPE, timeout=5, check=False)
        if result.returncode != 0:
            return None
        if b'Lost: 0 (0.00%)' not in result.stdout:
            return None
        if b'unreachable (type=3' in result.stdout:
            return None
        times = re.findall(r'Avg rtt: ([\d.]+)ms', result.stdout.decode())
        if len(times) != 1:
            return None
        return float(times[0])
    except subprocess.TimeoutExpired:
        return None


def test_web(ip: str) -> Optional[str]:
    try:
        response = requests.get(f'http://{ip}/saarctf', timeout=4)
        if response.status_code != 200:
            return f'status {response.status_code}'
        if response.text.strip() != 'saarctf-testbox':
            return f'unexpected text'
        return 'OK'
    except requests.Timeout:
        return 'unreachable'
    except requests.ConnectionError:
        return 'unreachable'
    except requests.RequestException as e:
        return 'error: ' + str(e)
