#!/bin/bash

set -e

if [ ! -f /mnt/vectorized/redpanda/pid ]; then
    exit 0
fi

pid=$(cat /mnt/vectorized/redpanda/pid)

if [ $pid == "" ]; then
    exit 0
fi

if ps -p $pid; then
    kill -9 $pid
fi

rm /mnt/vectorized/redpanda/pid