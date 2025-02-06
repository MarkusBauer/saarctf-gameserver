import base64
import hashlib
import hmac
import os
import random
import struct
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from saarctf_commons.config import config, load_default_config

"""
Generates valid flags

// Binary flag format (after b64 decode): 24 bytes
// = 32 bytes base64
// = 38 bytes including SAAR{}
// Truncated format: 24bytes => 32chars => 38chars total
struct __attribute__((__packed__)) FlagFormat {
	uint16_t tick;
	uint16_t team_id;
	uint16_t service_id;
	uint16_t payload;
	char mac[16]; // out of 32
};
"""


def generate_flag(team: int, service: int, game_tick: int | None = None) -> str:
    assert team < 2 ** 16
    assert service < 2 ** 16

    if not game_tick:
        game_tick = 1
    assert game_tick < 2 ** 16
    flag = struct.pack("<HHHH", game_tick, team, service, random.getrandbits(16))
    mac = hmac.new(config.SECRET_FLAG_KEY, flag, hashlib.sha256)
    flag += mac.digest()[:16]
    return f"SAAR{{{base64.b64encode(flag).replace(b'+', b'-').replace(b'/', b'_').decode()}}}"


if __name__ == "__main__":
    load_default_config()
    config.set_script()
    print("Key =", ", ".join(map(hex, config.SECRET_FLAG_KEY)))
    for i in range(10):
        print(
            generate_flag(
                int(sys.argv[1]) if len(sys.argv) > 1 else i,
                int(sys.argv[2]) if len(sys.argv) > 2 else 1,
            )
        )
