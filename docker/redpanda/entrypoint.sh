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

mkdir -p /mnt/vectorized/redpanda/data
mkdir -p /mnt/vectorized/redpanda/coredump

me=$(hostname)
myip="${redpandas[$me]}"

if [ "$me" == "redpanda1" ]; then
  rpk config bootstrap \
    --id ${node_ids[$me]} \
    --self $myip
else
  rpk config bootstrap \
    --id ${node_ids[$me]} \
    --self $myip \
    --ips "${redpandas[redpanda1]}"
fi

rpk config set redpanda.default_topic_partitions 1
rpk config set redpanda.default_topic_replications 3
rpk config set redpanda.transaction_coordinator_replication 3
rpk config set redpanda.id_allocator_replication 3
rpk config set redpanda.enable_leader_balancer false
rpk config set redpanda.enable_auto_rebalance_on_node_add false
rpk config set redpanda.enable_idempotence true
rpk config set redpanda.enable_transactions true
rpk config set redpanda.data_directory "/mnt/vectorized/redpanda/data"
rpk config set rpk.coredump_dir "/mnt/vectorized/redpanda/coredump"
rpk redpanda mode production
rpk redpanda tune all

cp /etc/redpanda/redpanda.yaml /mnt/vectorized/redpanda.yaml
chown -R ubuntu:ubuntu /etc/redpanda
chown ubuntu:ubuntu /mnt/vectorized/redpanda.yaml

rm -rf /mnt/vectorized/redpanda.nodes
for host in "${!redpandas[@]}"; do
  echo "${redpandas[$host]} ${node_ids[$host]}" >> /mnt/vectorized/redpanda.nodes
done
chown ubuntu:ubuntu /mnt/vectorized/redpanda.nodes

service ssh start
sleep infinity
