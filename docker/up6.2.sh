#!/usr/bin/env bash

set -e

docker-compose -f docker/docker-compose6.2.yaml --project-directory . up --detach