#!/bin/bash

set -e

nohup /bin/redpanda --redpanda-cfg /etc/redpanda/redpanda.yaml > /mnt/vectorized/redpanda/log 2>&1 & echo $! > /mnt/vectorized/redpanda/pid