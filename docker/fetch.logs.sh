#!/usr/bin/env bash

set -e

source=docker/bind_mounts/control/mnt/vectorized/experiments
mkdir -p results
if [ -d $source ]; then
  if [ "$(ls -A $source)" ]; then
    cp -r $source/* results/
  fi
fi
