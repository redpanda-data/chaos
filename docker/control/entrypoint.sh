#!/bin/bash

sleep 5s

declare -A ids=( ["redpanda1"]="0" ["redpanda2"]="1" ["redpanda3"]="2")

rm -rf /mnt/vectorized/redpanda.nodes

for name in "${!ids[@]}"; do
  ip=$(getent hosts $name | awk '{ print $1 }')
  id="${ids[$name]}"
  echo "$ip $id" >> /mnt/vectorized/redpanda.nodes
done

chown ubuntu:ubuntu /mnt/vectorized/redpanda.nodes

rm -rf /mnt/vectorized/client.nodes
client1ip=$(getent hosts client1 | awk '{ print $1 }')
echo "$client1ip 0" >> /mnt/vectorized/client.nodes
chown ubuntu:ubuntu /mnt/vectorized/client.nodes

sleep infinity