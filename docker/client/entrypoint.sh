#!/bin/bash

declare -A redpandas=( ["redpanda1"]="" ["redpanda2"]="" ["redpanda3"]="")
declare -A node_ids=( ["redpanda1"]="0" ["redpanda2"]="1" ["redpanda3"]="2")

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