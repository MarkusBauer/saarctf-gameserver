import socket
import sys
import telnetlib

from generate_flag import generate_flag

"""
USAGE: python3 submit_new_flags.py <count>
Submits <count> new and valid flags to localhost:31337
"""


HOST = "localhost"
PORT = 31337
COUNT = int(sys.argv[1])

conn = telnetlib.Telnet(HOST, PORT, 2)
print("Connected.")

print(f"Sending {COUNT} flags ...")
success = 0
for i in range(COUNT):
    conn.write((generate_flag(2, 1, 100) + "\n").encode())
    tmp = conn.read_until(b"\n")
    if tmp != b"[OK]\n":
        print(tmp.strip())
    else:
        success += 1

# half close
conn.get_socket().shutdown(socket.SHUT_WR)
conn.read_all()
# full close
conn.close()

print(f"Done. {success}")
if success != COUNT:
    sys.exit(1)
