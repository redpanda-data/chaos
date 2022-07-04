#!/usr/bin/env bash

set -e

./docker/rebuild4.sh
./docker/up4.sh
if ! ./docker/alive4.sh; then
  ./docker/down4.sh
  exit 1
fi
./docker/test.suite.sh suites/test_suite_idempotency.json
./docker/test.suite.sh suites/test_suite_list_offsets.json
./docker/test.suite.sh suites/test_suite_reads_writes.json
./docker/fetch.logs.sh
./docker/down4.sh

./docker/rebuild6.sh
./docker/up6.sh
./docker/test.suite.sh suites/test_suite_tx_money.json
./docker/test.suite.sh suites/test_suite_tx_reads_writes.json
./docker/test.suite.sh suites/test_suite_rw_subscribe.json
./docker/fetch.logs.sh
./docker/down6.sh

./docker/rebuild6.2.sh
./docker/up6.2.sh
./docker/test.suite.sh suites/test_suite_tx_subscribe.json
./docker/fetch.logs.sh
./docker/down6.2.sh

python3 harness/combine.results.py
