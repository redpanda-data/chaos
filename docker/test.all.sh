#!/usr/bin/env bash

set -e

./docker/rebuild4.sh || exit 10 # use arbitrary exit code to retry on
./docker/up4.sh
if ! ./docker/ready4.sh; then
  echo "cluster did not reach ready state"
  ./docker/down4.sh
  exit 1
fi
./docker/test.suite.sh suites/test_suite_idempotency.json
./docker/test.suite.sh suites/test_suite_list_offsets.json
./docker/test.suite.sh suites/test_suite_reads_writes.json
./docker/fetch.logs.sh
./docker/down4.sh

./docker/rebuild6.sh || exit 10 # use arbitrary exit code to retry on
./docker/up6.sh
if ! ./docker/ready6.sh; then
  ./docker/down6.sh
  exit 1
fi
./docker/test.suite.sh suites/test_suite_tx_compact.json
./docker/test.suite.sh suites/test_suite_tx_money.json
./docker/test.suite.sh suites/test_suite_tx_reads_writes.json
./docker/test.suite.sh suites/test_suite_rw_subscribe.json
./docker/fetch.logs.sh
./docker/down6.sh

./docker/rebuild6.2.sh || exit 10 # use arbitrary exit code to retry on
./docker/up6.2.sh
if ! ./docker/ready6.2.sh; then
  ./docker/down6.2.sh
  exit 1
fi
./docker/test.suite.sh suites/test_suite_tx_subscribe.json
./docker/fetch.logs.sh
./docker/down6.2.sh

python3 harness/combine.results.py
