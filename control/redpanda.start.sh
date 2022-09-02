#!/bin/bash

set -e

nohup /bin/redpanda --logger-log-level tx=$1 --redpanda-cfg /etc/redpanda/redpanda.yaml --smp 1 >/mnt/vectorized/redpanda/log.$(date +%s) 2>&1 &
echo $! >/mnt/vectorized/redpanda/pid
