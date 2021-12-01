#!/usr/bin/env bash

set -e

./docker/rebuild3.sh
./docker/up3.sh
./docker/test.suite.sh test_suite_all.json
./docker/fetch.logs.sh
./docker/down3.sh
python3 harness/combine.results.py