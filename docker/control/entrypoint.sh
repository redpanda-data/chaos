#!/bin/bash

set -e

MAX_ATTEMPS=60
LOG=/mnt/vectorized/entrypoint/entrypoint.log

echo "starting control node" >>$LOG

for DEB in $DEB_FILE_LIST; do
  if [[ ! -r "/mnt/vectorized/deb/$DEB" ]]; then
    echo "/mnt/vectorized/deb/$DEB doesn't exist" >>$LOG
    exit 1
  fi
  dpkg --force-confold -i "/mnt/vectorized/deb/$DEB"
done

systemctl disable redpanda
systemctl disable wasm_engine

declare -A clients=(["client1"]="")

for ((i = 1; i <= WORKLOAD_CLUSTER_SIZE; i++)); do
  clients["client$i"]=""
done

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

for host in "${!clients[@]}"; do
  attempt=0
  clients[$host]=$(getent hosts $host | awk '{ print $1 }')
  while [ "${clients[$host]}" == "" ]; do
    echo "can't resolve client host $host" >>$LOG
    sleep 1s
    clients[$host]=$(getent hosts $host | awk '{ print $1 }')
    ((attempt = attempt + 1))
    if [[ $attempt -eq $MAX_ATTEMPS ]]; then
      echo "retry limit exhausted" >>$LOG
      exit 1
    fi
  done
  echo "$host (client node) resolves to ${clients[$host]}" >>$LOG
done

rm -rf /mnt/vectorized/redpanda.nodes
for host in "${!redpandas[@]}"; do
  echo "${redpandas[$host]} ${node_ids[$host]}" >>/mnt/vectorized/redpanda.nodes
done
chown ubuntu:ubuntu /mnt/vectorized/redpanda.nodes

rm -rf /mnt/vectorized/client.nodes
client_node_id=0
for host in "${!clients[@]}"; do
  echo "${clients[$host]} $client_node_id" >>/mnt/vectorized/client.nodes
  ((client_node_id = client_node_id + 1))
done
chown ubuntu:ubuntu /mnt/vectorized/client.nodes

rm -rf /home/ubuntu/.ssh/known_hosts
for host in "${!redpandas[@]}"; do
  attempt=0
  until ssh-keyscan "${redpandas[$host]}" >/dev/null 2>&1; do
    echo "can't ssh-keyscan ${redpandas[$host]} (redpanda host $host)" >>$LOG
    sleep 1s
    ((attempt = attempt + 1))
    if [[ $attempt -eq $MAX_ATTEMPS ]]; then
      echo "retry limit exhausted" >>$LOG
      exit 1
    fi
  done
  ssh-keyscan "${redpandas[$host]}" 2>/dev/null >>/home/ubuntu/.ssh/known_hosts
  echo "ssh-keyscan ${redpandas[$host]}" >>$LOG
done

for host in "${!clients[@]}"; do
  attempt=0
  until ssh-keyscan "${clients[$host]}" >/dev/null 2>&1; do
    echo "can't ssh-keyscan ${clients[$host]} (client host $host)" >>$LOG
    sleep 1s
    ((attempt = attempt + 1))
    if [[ $attempt -eq $MAX_ATTEMPS ]]; then
      echo "retry limit exhausted" >>$LOG
      exit 1
    fi
  done
  ssh-keyscan "${clients[$host]}" 2>/dev/null >>/home/ubuntu/.ssh/known_hosts
  echo "ssh-keyscan ${clients[$host]}" >>$LOG
done
chown ubuntu:ubuntu /home/ubuntu/.ssh/known_hosts

touch /mnt/vectorized/ready

echo "node is ready" >>$LOG

sleep infinity
