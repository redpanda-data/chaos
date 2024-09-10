#!/usr/bin/env bash

set -e

if [ "${COMPOSE_PROJECT_NAME}" == "" ]; then
  echo "COMPOSE_PROJECT_NAME is not set"
  exit 1
fi

MAX_ATTEMPS=60

abort() {
  for node in redpanda1 redpanda2 redpanda3 redpanda4 client1 control; do
    echo "## $node log"
    cat ./docker/bind_mounts/${COMPOSE_PROJECT_NAME}-$node/mnt/vectorized/entrypoint/entrypoint.log
    echo "--------------"
  done
  exit 1
}

attempt=0
for node in redpanda1 redpanda2 redpanda3 redpanda4 client1 control; do
  until docker exec $COMPOSE_PROJECT_NAME-$node /bin/bash -c "[ -f /mnt/vectorized/ready ]" 2>/dev/null; do
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
