#!/usr/bin/env bash
case "$1" in
    "open")
        curl 'http://127.0.0.1:5000/overview/set_vpn' --silent --show-error --compressed -H 'Content-Type: application/json;charset=utf-8' --data '{"state":true}'
        ;;
    "close")
        curl 'http://127.0.0.1:5000/overview/set_vpn' --silent --show-error --compressed -H 'Content-Type: application/json;charset=utf-8' --data '{"state":false}'
        ;;
    *)
        echo -e "Unkown argument.\nSpecify one of: open, close"
        exit 1
        ;;
esac
