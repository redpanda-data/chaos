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

if [ "$COMPOSE_PROJECT_NAME" == "" ]; then
  echo "Please set COMPOSE_PROJECT_NAME environment variable"
  exit 1
fi

docker compose -f docker/docker-compose6.2.yaml --project-directory . down --remove-orphans || true
docker compose -f docker/docker-compose6.2.yaml --project-directory . rm -f || true
docker compose -f docker/docker-compose6.yaml --project-directory . down --remove-orphans || true
docker compose -f docker/docker-compose6.yaml --project-directory . rm -f || true
docker compose -f docker/docker-compose4.yaml --project-directory . down --remove-orphans || true
docker compose -f docker/docker-compose4.yaml --project-directory . rm -f || true

if [ ! -f id_ed25519 ]; then
  if [ "$SKIP_SSH_KEYGEN" == "1" ]; then
    echo "SKIP_SSH_KEYGEN is set.  Not generating id_ed25519 file"
  else
    echo "Generating id_ed25519 file"
    ssh-keygen -t ed25519 -f id_ed25519 -N ""
  fi
else
  echo "id_ed25519 already exists - not regenerating"
fi

rm -rfv ./docker/bind_mounts/$COMPOSE_PROJECT_NAME-*

for redpanda in redpanda1 redpanda2 redpanda3 redpanda4 redpanda5 redpanda6; do
  mkdir -m 777 -p ./docker/bind_mounts/$COMPOSE_PROJECT_NAME-$redpanda/mnt/vectorized/redpanda/data
  mkdir -m 777 -p ./docker/bind_mounts/$COMPOSE_PROJECT_NAME-$redpanda/mnt/vectorized/redpanda/coredump
  mkdir -m 777 -p ./docker/bind_mounts/$COMPOSE_PROJECT_NAME-$redpanda/mnt/vectorized/entrypoint
done

mkdir -m 777 -p ./docker/bind_mounts/$COMPOSE_PROJECT_NAME-control/mnt/vectorized/experiments
mkdir -m 777 -p ./docker/bind_mounts/$COMPOSE_PROJECT_NAME-control/mnt/vectorized/entrypoint

for client in client1 client2; do
  mkdir -m 777 -p ./docker/bind_mounts/$COMPOSE_PROJECT_NAME-$client/mnt/vectorized/workloads/logs
  mkdir -m 777 -p ./docker/bind_mounts/$COMPOSE_PROJECT_NAME-$client/mnt/vectorized/entrypoint
done

docker compose -f docker/docker-compose6.2.yaml --project-directory . build --build-arg USER_ID=$(id -u $(whoami))
