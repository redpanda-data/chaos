#!/bin/bash

set -e

nohup /bin/redpanda --default-log-level $1 --logger-log-level=$2 --logger-log-level=exception=warn --logger-log-level=io=info --redpanda-cfg /etc/redpanda/redpanda.yaml --smp 1 >/mnt/vectorized/redpanda/log.$(date +%s) 2>&1 &
echo $! >/mnt/vectorized/redpanda/pid
