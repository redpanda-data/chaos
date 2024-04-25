#!/bin/bash

set -e

MAX_ATTEMPS=30
LOG=/mnt/vectorized/entrypoint/entrypoint.log

echo "starting client node" >>$LOG

for DEB in $DEB_FILE_LIST; do
  if [[ ! -r "/mnt/vectorized/deb/$DEB" ]]; then
    echo "/mnt/vectorized/deb/$DEB doesn't exist" >>$LOG
    exit 1
  fi
  dpkg --force-confold -i "/mnt/vectorized/deb/$DEB"
done

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
    echo "can't resolve redpanda host $host" >>$LOG
    sleep 1s
    redpandas[$host]=$(getent hosts $host | awk '{ print $1 }')
    ((attempt = attempt + 1))
    if [[ $attempt -eq $MAX_ATTEMPS ]]; then
      echo "retry limit exhausted" >>$LOG
      exit 1
    fi
  done
  echo "$host (redpanda node) resolves to ${redpandas[$host]}" >>$LOG
done

rm -rf /mnt/vectorized/redpanda.nodes
for host in "${!redpandas[@]}"; do
  echo "${redpandas[$host]} ${node_ids[$host]}" >>/mnt/vectorized/redpanda.nodes
done
chown ubuntu:ubuntu /mnt/vectorized/redpanda.nodes

echo "starting ssh" >>$LOG

service ssh start

touch /mnt/vectorized/ready

echo "node is ready" >>$LOG

sleep infinity
