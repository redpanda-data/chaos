#!/usr/bin/env bash

set -e

docker-compose -f docker/docker-compose4.yaml --project-directory . up --detach
