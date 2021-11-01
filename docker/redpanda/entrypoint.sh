#!/bin/bash

sleep 5s

mkdir -p /mnt/vectorized/redpanda/data
mkdir -p /mnt/vectorized/redpanda/coredump

declare -A ids=( ["redpanda1"]="0" ["redpanda2"]="1" ["redpanda3"]="2")

me=$(hostname)
myip=$(getent hosts $me | awk '{ print $1 }')
seedip=$(getent hosts redpanda1 | awk '{ print $1 }')

if [ "$me" == "redpanda1" ]; then
  rpk config bootstrap \
    --id 0 \
    --self $myip
else
  rpk config bootstrap \
    --id ${ids[$me]} \
    --self $myip \
    --ips $seedip
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

rm -rf /mnt/vectorized/redpanda.nodes

for name in redpanda1 redpanda2 redpanda3; do
  ip=$(getent hosts $name | awk '{ print $1 }')
  id=${ids[$name]}
  echo "$ip $id" >> /mnt/vectorized/redpanda.nodes
done

chown ubuntu:ubuntu /mnt/vectorized/redpanda.nodes

service ssh start
sleep infinity