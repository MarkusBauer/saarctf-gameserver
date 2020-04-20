#!/usr/bin/env python3

import sys
import typing as t

import requests

URL = "http://127.0.0.1:5000/overview/set_timing"


def start_ctf() -> None:
    requests.post(URL, json={"state": 3}).raise_for_status()


def pause_ctf() -> None:
    requests.post(URL, json={"state": 2}).raise_for_status()


def stop_ctf() -> None:
    requests.post(URL, json={"state": 1}).raise_for_status()


def set_roundtime(roundtime: int) -> None:
    requests.post(URL, json={"roundtime": roundtime}).raise_for_status()


def set_lastround(lastround: int) -> None:
    requests.post(URL, json={"lastround": lastround}).raise_for_status()


def main() -> None:
    if sys.argv[1] == "start":
        start_ctf()
    elif sys.argv[1] == "pause":
        pause_ctf()
    elif sys.argv[1] == "stop":
        stop_ctf()
    elif sys.argv[1] == "roundtime":
        set_roundtime(int(sys.argv[2]))
    elif sys.argv[1] == "lastround":
        set_lastround(int(sys.argv[2]))
    else:
        print(
            f"Unknown flag: {sys.argv[1]}\nUse one of: start, pause, stop, roundtime, lastround"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
