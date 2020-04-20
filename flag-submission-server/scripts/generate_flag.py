import base64
import binascii
import hashlib
import hmac
import json
import random
import struct
import sys
import typing as t

with open("../../config.json", "rb") as f:
    SECRET_KEY = binascii.unhexlify(json.loads(f.read())["secret_flags"])

"""
Generates valid flags

// Binary flag format (after b64 decode): 24 bytes
// = 32 bytes base64
// = 38 bytes including SAAR{}
// Truncated format: 24bytes => 32chars => 38chars total
struct __attribute__((__packed__)) FlagFormat {
	uint16_t round;
	uint16_t team_id;
	uint16_t service_id;
	uint16_t payload;
	char mac[16]; // out of 32
};
"""

def generate_flag(team:int, service:int, game_round:t.Optional[int]=None) -> str:
    assert team < 2**16
    assert service < 2**16

    if not game_round:
        game_round = 1
    assert game_round < 2**16
    flag = struct.pack("<HHHH", game_round, team, service, random.getrandbits(16))
    mac = hmac.new(SECRET_KEY, flag, hashlib.sha256)
    flag += mac.digest()[:16]
    return f"SAAR{{{base64.b64encode(flag).replace(b'+', b'-').replace(b'/', b'_').decode()}}}"


if __name__ == "__main__":
    print("Key =", ", ".join(map(hex, SECRET_KEY)))
    for i in range(10):
        print(
            generate_flag(
                int(sys.argv[1]) if len(sys.argv) > 1 else i,
                int(sys.argv[2]) if len(sys.argv) > 2 else 1,
            )
        )
