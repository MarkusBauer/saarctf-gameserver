import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

API_SERVER = os.getenv("API_SERVER", "http://ctf.localhost")
API_BASE = os.getenv("API_BASE", "/api/router/")
API_TOKEN = os.getenv("API_TOKEN", None)
API_CONCURRENCY = int(os.getenv("API_CONCURRENCY", 1))

KEYSTORE_PATH: str = os.getenv("KEYSTORE_PATH", "./keystore.json")

BASE_DIR: Path = Path(__file__).parent
INTERFACE_UP_HOOKS: list[Path] = [
    BASE_DIR / "../../vpn/bpf/install.sh",
    BASE_DIR / "../../vpn/ratelimit/install.sh",
]

# import config from saarctf common config, if available
try:
    from saarctf_commons import config

    config.load_default_config()
    wg = config.current_config.WIREGUARD_SYNC
    if wg:
        API_SERVER = wg.api_server
        API_BASE = wg.api_base
        API_TOKEN = wg.api_token
        API_CONCURRENCY = wg.api_concurrency
        KEYSTORE_PATH = str(config.current_config.basedir / "keystore.json")
        print("Imported saarctf settings")
    else:
        print("Wireguard sync not configured in saarctf settings")
except ImportError:
    print("No saarctf settings available")
