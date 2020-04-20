#!/usr/bin/env python3

import socket
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 1234

s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
s.bind(('0.0.0.0', PORT))
s.listen(5)
print(f'Listening on port {PORT} ...')

while True:
    conn, addr = s.accept()
    conn.settimeout(7)
    data = conn.recv(4096)
    print(f'Connection from {addr}: "{data.decode("utf-8")}"')
    response = f'[OK] with {addr[0]}:{addr[1]}\nMessage: "{data.decode()}"'
    if len(sys.argv) > 2:
        response += ' from '+sys.argv[2]
    conn.send(response.encode())
    conn.close()
