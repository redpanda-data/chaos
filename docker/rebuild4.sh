#!/usr/bin/env bash

set -e

if [ "$DEB_DIR" == "" ]; then
  echo "env var $DEB_DIR must contain a dir path where deb files live"
  exit 1
fi
if [ "$DEB_FILE_LIST" == "" ]; then
  echo "env var $DEB_FILE_LIST must contain a list of deb filenames, in space delimited format"
  exit 1
fi

docker compose -f docker/docker-compose6.2.yaml --project-directory . down --remove-orphans || true
docker compose -f docker/docker-compose6.2.yaml --project-directory . rm -f || true
docker compose -f docker/docker-compose6.yaml --project-directory . down --remove-orphans || true
docker compose -f docker/docker-compose6.yaml --project-directory . rm -f || true
docker compose -f docker/docker-compose4.yaml --project-directory . down --remove-orphans || true
docker compose -f docker/docker-compose4.yaml --project-directory . rm -f || true

if [ ! -f id_ed25519 ]; then
  ssh-keygen -t ed25519 -f id_ed25519 -N ""
fi

rm -rf ./docker/bind_mounts

for redpanda in redpanda1 redpanda2 redpanda3 redpanda4; do
  mkdir -p ./docker/bind_mounts/$redpanda/mnt/vectorized/redpanda/data
  mkdir -p ./docker/bind_mounts/$redpanda/mnt/vectorized/redpanda/coredump
  mkdir -p ./docker/bind_mounts/$redpanda/mnt/vectorized/entrypoint
done

mkdir -p ./docker/bind_mounts/control/mnt/vectorized/experiments
mkdir -p ./docker/bind_mounts/control/mnt/vectorized/entrypoint

mkdir -p ./docker/bind_mounts/client1/mnt/vectorized/workloads/logs
mkdir -p ./docker/bind_mounts/client1/mnt/vectorized/entrypoint

chmod -R a+rw ./docker/bind_mounts

docker compose -f docker/docker-compose4.yaml --project-directory . build --build-arg USER_ID=$(id -u $(whoami))
