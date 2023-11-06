#!/bin/bash

set -e

MAX_ATTEMPS=30
LOG=/mnt/vectorized/entrypoint/entrypoint.log

echo "starting redpanda node" >>$LOG

if [[ ! -r /mnt/vectorized/redpanda.deb ]]; then
  echo "/mnt/vectorized/redpanda.deb doesn't exist" >>$LOG
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
    echo "can't resolve redpanda host $host" >>$LOG
    sleep 1s
    redpandas[$host]=$(getent hosts $host | awk '{ print $1 }')
    ((attempt = attempt + 1))
    if [[ $attempt -eq $MAX_ATTEMPS ]]; then
      echo "retry limit exhausted" >>$LOG
      exit 1
    fi
  done
  echo "$host resolves to ${redpandas[$host]}" >>$LOG
done

mkdir -p /mnt/vectorized/redpanda/data
mkdir -p /mnt/vectorized/redpanda/coredump

me=$(hostname)
myip="${redpandas[$me]}"

echo "configuring redpanda" >>$LOG

if [ "$me" == "redpanda1" ]; then
  rpk config bootstrap \
    --id ${node_ids[$me]} \
    --self $myip &>>$LOG
else
  rpk config bootstrap \
    --id ${node_ids[$me]} \
    --self $myip \
    --ips "${redpandas[redpanda1]}" &>>$LOG
fi

rpk config set redpanda.default_topic_partitions 1
rpk config set redpanda.default_topic_replications 3
rpk config set redpanda.transaction_coordinator_replication 3
rpk config set redpanda.id_allocator_replication 3
rpk config set redpanda.enable_leader_balancer false
rpk config set redpanda.enable_auto_rebalance_on_node_add false
rpk config set redpanda.enable_idempotence true
rpk config set redpanda.enable_transactions true
rpk config set redpanda.advertised_rpc_api "{address: $me, port: 33145}"
rpk config set redpanda.advertised_kafka_api "[{address: $me, port: 9092}]"
rpk config set redpanda.data_directory "/mnt/vectorized/redpanda/data"
rpk config set rpk.coredump_dir "/mnt/vectorized/redpanda/coredump"
echo "setting production mode"
rpk redpanda mode production
echo "tuning all"
if ! rpk redpanda tune all &>>$LOG; then
  echo "tuning returned non zero error code" >>$LOG
fi

echo "configured" >>$LOG

cp /etc/redpanda/redpanda.yaml /mnt/vectorized/redpanda.yaml
chown -R ubuntu:ubuntu /etc/redpanda
chown ubuntu:ubuntu /mnt/vectorized/redpanda.yaml

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
