#!/usr/bin/env bash

set -e

./docker/rebuild.sh
./docker/up.sh
./docker/test.test.sh writing_reads_writes/pause_leader.json
./docker/fetch.logs.sh
./docker/down.sh