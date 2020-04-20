#!/usr/bin/env bash

set -e

# TODO some config here? Or just use a symlink?
FOLDER="/tmp/teamtraffic"

mkdir -p "$FOLDER"
mv "$1" "$FOLDER/"
