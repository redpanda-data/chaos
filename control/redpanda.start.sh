#!/bin/bash

set -e

nohup /bin/redpanda --redpanda-cfg /etc/redpanda/redpanda.yaml --smp 1 > /mnt/vectorized/redpanda/log.$(date +%s) 2>&1 & echo $! > /mnt/vectorized/redpanda/pid