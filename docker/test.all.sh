#!/usr/bin/env bash

set -e

./docker/rebuild.sh
./docker/up.sh
./docker/test.suite.sh test_suite_all.json
./docker/fetch.logs.sh
./docker/down.sh
python3 harness/combine.results.py