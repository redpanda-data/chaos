#!/usr/bin/env bash

set -e

if [ "${COMPOSE_PROJECT_NAME}" == "" ]; then
  echo "COMPOSE_PROJECT_NAME is not set"
  exit 1
fi

docker compose -f docker/docker-compose4.yaml --project-directory . down
