#!/usr/bin/env bash

set -e

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

for redpanda in redpanda1 redpanda2 redpanda3 redpanda4 redpanda5 redpanda6; do
  mkdir -p ./docker/bind_mounts/$redpanda/mnt/vectorized/redpanda/data
  mkdir -p ./docker/bind_mounts/$redpanda/mnt/vectorized/redpanda/coredump
  mkdir -p ./docker/bind_mounts/$redpanda/mnt/vectorized/entrypoint
done

mkdir -p ./docker/bind_mounts/control/mnt/vectorized/experiments
mkdir -p ./docker/bind_mounts/control/mnt/vectorized/entrypoint

for client in client1 client2; do
  mkdir -p ./docker/bind_mounts/$client/mnt/vectorized/workloads/logs
  mkdir -p ./docker/bind_mounts/$client/mnt/vectorized/entrypoint
done

chmod -R a+rw ./docker/bind_mounts

docker compose -f docker/docker-compose6.2.yaml --project-directory . build --build-arg USER_ID=$(id -u $(whoami))
