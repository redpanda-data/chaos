#!/bin/bash

sleep 5s

declare -A ids=( ["redpanda1"]="0" ["redpanda2"]="1" ["redpanda3"]="2")

rm -rf /mnt/vectorized/redpanda.nodes

for name in redpanda1 redpanda2 redpanda3; do
  ip=$(getent hosts $name | awk '{ print $1 }')
  id=${ids[$name]}
  echo "$ip $id" >> /mnt/vectorized/redpanda.nodes
done

chown ubuntu:ubuntu /mnt/vectorized/redpanda.nodes

service ssh start
sleep infinity