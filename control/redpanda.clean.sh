#!/bin/bash

set -e

rm -rf /mnt/vectorized/redpanda/data/*
rm -rf /mnt/vectorized/redpanda/coredump/*
rm -rf /mnt/vectorized/redpanda/log.*
rm -rf /mnt/vectorized/redpanda/pid
cp /mnt/vectorized/redpanda.yaml /etc/redpanda/redpanda.yaml