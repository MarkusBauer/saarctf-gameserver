#!/usr/bin/env python3

import socket
import sys

PORT = int(sys.argv[2]) if len(sys.argv) > 2 else 1234
MESSAGE = sys.argv[3] if len(sys.argv) > 3 else '<no message>'

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.settimeout(7)
s.connect((sys.argv[1], PORT))
s.sendall(MESSAGE.encode('utf-8'))
data = s.recv(4096)
s.close()
print(data.decode())
