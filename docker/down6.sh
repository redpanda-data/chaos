#!/usr/bin/env bash

set -e

docker-compose -f docker/docker-compose6.yaml --project-directory . down
