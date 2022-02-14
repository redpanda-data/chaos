#!/bin/bash

if [[ ! -r /mnt/vectorized/redpanda.deb ]]; then
  echo 'error: unable to read /mnt/vectorized/redpanda.deb'
  exit 1
fi

dpkg --force-confold -i /mnt/vectorized/redpanda.deb
systemctl disable redpanda
systemctl disable wasm_engine

declare -A redpandas
declare -A node_ids

for (( i=1; i<=$REDPANDA_CLUSTER_SIZE; i++ )); do  
  redpandas["redpanda$i"]=""
  node_ids["redpanda$i"]="$i"
done

for host in "${!redpandas[@]}"; do
  redpandas[$host]=$(getent hosts $host | awk '{ print $1 }')
  while [ "${redpandas[$host]}" == "" ]; do
    sleep 1s
    redpandas[$host]=$(getent hosts $host | awk '{ print $1 }')
  done
done

rm -rf /mnt/vectorized/redpanda.nodes
for host in "${!redpandas[@]}"; do
  echo "${redpandas[$host]} ${node_ids[$host]}" >> /mnt/vectorized/redpanda.nodes
done
chown ubuntu:ubuntu /mnt/vectorized/redpanda.nodes

service ssh start
sleep infinity
