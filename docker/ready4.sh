#!/usr/bin/env bash

set -e

MAX_ATTEMPS=10

abort() {
  echo "## control log"
  cat ./docker/bind_mounts/control/mnt/vectorized/entrypoint/entrypoint.log
  echo "--------------"
  echo "## client log"
  cat ./docker/bind_mounts/client1/mnt/vectorized/entrypoint/entrypoint.log
  echo "--------------"
  for redpanda in redpanda1 redpanda2 redpanda3 redpanda4; do
    echo "## $redpanda log"
    cat ./docker/bind_mounts/$redpanda/mnt/vectorized/entrypoint/entrypoint.log
    echo "--------------"
  done
  exit 1
}

attempt=0

for redpanda in redpanda1 redpanda2 redpanda3 redpanda4; do
  until docker exec $redpanda /bin/bash -c "[ -f /mnt/vectorized/ready ]" 2>/dev/null; do
    echo "$redpanda node isn't initialized"
    sleep 1s
    ((attempt = attempt + 1))
    if [[ $attempt -eq $MAX_ATTEMPS ]]; then
      echo "retry limit exhausted; cluster isn't ready"
      abort
    fi
  done
done

until docker exec client1 /bin/bash -c "[ -f /mnt/vectorized/ready ]" 2>/dev/null; do
  echo "client1 node isn't initialized"
  sleep 1s
  ((attempt = attempt + 1))
  if [[ $attempt -eq $MAX_ATTEMPS ]]; then
    echo "retry limit exhausted; cluster isn't ready"
    abort
  fi
done

until docker exec control /bin/bash -c "[ -f /mnt/vectorized/ready ]" 2>/dev/null; do
  echo "control node isn't initialized"
  sleep 1s
  ((attempt = attempt + 1))
  if [[ $attempt -eq $MAX_ATTEMPS ]]; then
    echo "retry limit exhausted; cluster isn't ready"
    abort
  fi
done

echo "cluster is ready"
