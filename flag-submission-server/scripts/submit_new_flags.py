import sys
from pwn import remote

from generate_flag import generate_flag, config, load_default_config

"""
USAGE: python3 submit_new_flags.py <count>
Submits <count> new and valid flags to localhost:31337
"""

load_default_config()
config.set_script()

HOST = "localhost"
PORT = 31337
COUNT = int(sys.argv[1])

conn = remote(HOST, PORT)
print("Connected.")

print(f"Sending {COUNT} flags ...")
success = 0
for i in range(COUNT):
    conn.write((generate_flag(2, 1, 100) + "\n").encode())
    tmp = conn.readuntil(b"\n")
    if tmp != b"[OK]\n":
        print(tmp.strip())
    else:
        success += 1

# half close
conn.shutdown()
conn.readall()
# full close
conn.close()

print(f"Done. {success}")
if success != COUNT:
    sys.exit(1)
