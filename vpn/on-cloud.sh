#!/usr/bin/env bash

set -e
source /etc/profile.d/env.sh 2>/dev/null || true
cd "$( dirname "${BASH_SOURCE[0]}" )"

./$1 "$2"
