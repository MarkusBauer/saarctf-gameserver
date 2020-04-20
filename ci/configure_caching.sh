#!/usr/bin/env bash
set -euxo pipefail

# Check that the ulimit value is not too high as this is a problem for rabbitmq
if [ "$(ulimit -n)" -gt 1100000 ]
then
    echo "The ulimit for open file descriptors is very large:" "$(ulimit -n)"
    echo This may be a problem for rabbitmq and lead to hangs in the containers.
    exit 1
fi

# Ensure cache directories exist
mkdir -p \
  "$CI_PROJECT_DIR"/.cache/apt/lists/partial \
  "$CI_PROJECT_DIR"/.cache/apt/archives/partial \
  "$CI_PROJECT_DIR"/.cache/pip \
  "$CI_PROJECT_DIR"/.cache/npm


# Configure APT for caching
echo "dir::state::lists    $CI_PROJECT_DIR/.cache/apt/lists;" >> /etc/apt/apt.conf
echo "dir::cache::archives    $CI_PROJECT_DIR/.cache/apt/archives;" >> /etc/apt/apt.conf
