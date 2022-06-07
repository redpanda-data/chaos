#!/bin/bash

set -e

if [ ! -f /mnt/vectorized/workloads/logs/rw-subscribe.pid ]; then
  exit 0
fi

pid=$(cat /mnt/vectorized/workloads/logs/rw-subscribe.pid)

if [ $pid == "" ]; then
  exit 0
fi

if ps -p $pid; then
  kill -9 $pid
fi

rm /mnt/vectorized/workloads/logs/rw-subscribe.pid
