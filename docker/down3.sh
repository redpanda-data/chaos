#!/usr/bin/env bash

set -e

docker-compose -f docker/docker-compose3.yaml --project-directory . down