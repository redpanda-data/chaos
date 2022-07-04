#!/bin/bash

set -e

MAX_ATTEMPS=30

echo "starting client node" >>/mnt/vectorized/entrypoint/entrypoint.log

if [[ ! -r /mnt/vectorized/redpanda.deb ]]; then
  echo "/mnt/vectorized/redpanda.deb doesn't exist" >>/mnt/vectorized/entrypoint/entrypoint.log
  exit 1
fi

dpkg --force-confold -i /mnt/vectorized/redpanda.deb
systemctl disable redpanda
systemctl disable wasm_engine

declare -A redpandas
declare -A node_ids

for ((i = 1; i <= REDPANDA_CLUSTER_SIZE; i++)); do
  redpandas["redpanda$i"]=""
  node_ids["redpanda$i"]="$i"
done

for host in "${!redpandas[@]}"; do
  attempt=0
  redpandas[$host]=$(getent hosts $host | awk '{ print $1 }')
  while [ "${redpandas[$host]}" == "" ]; do
    echo "can't resolve redpanda host $host" >>/mnt/vectorized/entrypoint/entrypoint.log
    sleep 1s
    redpandas[$host]=$(getent hosts $host | awk '{ print $1 }')
    ((attempt = attempt + 1))
    if [[ $attempt -eq $MAX_ATTEMPS ]]; then
      echo "retry limit exhausted" >>/mnt/vectorized/entrypoint/entrypoint.log
      exit 1
    fi
  done
  echo "$host (redpanda node) resolves to ${redpandas[$host]}" >>/mnt/vectorized/entrypoint/entrypoint.log
done

rm -rf /mnt/vectorized/redpanda.nodes
for host in "${!redpandas[@]}"; do
  echo "${redpandas[$host]} ${node_ids[$host]}" >>/mnt/vectorized/redpanda.nodes
done
chown ubuntu:ubuntu /mnt/vectorized/redpanda.nodes

echo "starting ssh" >>/mnt/vectorized/entrypoint/entrypoint.log

service ssh start

touch /mnt/vectorized/ready

echo "node is ready" >>/mnt/vectorized/entrypoint/entrypoint.log

sleep infinity
