#!/usr/bin/env bash

set -e

MAX_ATTEMPS=60

abort() {
  for node in redpanda1 redpanda2 redpanda3 redpanda4 redpanda5 redpanda6 client1 client2 control; do
    echo "## $node log"
    cat ./docker/bind_mounts/$node/mnt/vectorized/entrypoint/entrypoint.log
    echo "--------------"
  done
  exit 1
}

attempt=0
for node in redpanda1 redpanda2 redpanda3 redpanda4 redpanda5 redpanda6 client1 client2 control; do
  until docker exec $node /bin/bash -c "[ -f /mnt/vectorized/ready ]" 2>/dev/null; do
    echo "node $node isn't initialized"
    sleep 1
    ((attempt = attempt + 1))
    if [[ $attempt -eq $MAX_ATTEMPS ]]; then
      echo "retry limit exhausted; cluster isn't ready"
      abort
    fi
  done
done

echo "cluster is ready"
