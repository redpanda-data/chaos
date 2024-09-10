#!/usr/bin/env bash

set -e

time ./docker_parallel_runner.py \
  --suite suites/test_suite_list_offsets.json:4:1 \
  --suite suites/test_suite_idempotency.json:4:1 \
  --suite suites/test_suite_reads_writes.json:4:1 \
  --suite suites/test_suite_tx_compact.json:6:1 \
  --suite suites/test_suite_tx_money.json:6:1 \
  --suite suites/test_suite_tx_reads_writes.json:6:1 \
  --suite suites/test_suite_rw_subscribe_1.json:6:1 \
  --suite suites/test_suite_rw_subscribe_2.json:6:1 \
  --suite suites/test_suite_tx_subscribe_1.json:6:2 \
  --suite suites/test_suite_tx_subscribe_2.json:6:2 \
  --suite suites/test_suite_tx_subscribe_3.json:6:2

time python3 harness/combine.results.py
