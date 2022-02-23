#!/bin/bash

set -e

if [ ! -f /mnt/vectorized/redpanda/pid ]; then
  echo "NO"
  exit 0
fi

pid=$(cat /mnt/vectorized/redpanda/pid)

if [ $pid == "" ]; then
  echo "NO"
  exit 0
fi

if ps -p $pid; then
  kill -STOP $pid
  echo "YES"
else
  echo "NO"
fi
