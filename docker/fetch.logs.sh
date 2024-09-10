#!/usr/bin/env bash

set -e

if [ "${COMPOSE_PROJECT_NAME}" == "" ]; then
  echo "COMPOSE_PROJECT_NAME is not set"
  exit 1
fi

source=docker/bind_mounts/${COMPOSE_PROJECT_NAME}-control/mnt/vectorized/experiments
mkdir -p results
if [ -d $source ]; then
  if [ "$(ls -A $source)" ]; then
    cp -r $source/* results/
  fi
fi
