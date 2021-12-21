#!/bin/bash

declare -A clients=( ["client1"]="")

for (( i=1; i<=$WORKLOAD_CLUSTER_SIZE; i++ )); do  
  clients["client$i"]=""
done

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

for host in "${!clients[@]}"; do
  clients[$host]=$(getent hosts $host | awk '{ print $1 }')
  while [ "${clients[$host]}" == "" ]; do
    sleep 1s
    clients[$host]=$(getent hosts $host | awk '{ print $1 }')
  done
done

rm -rf /mnt/vectorized/redpanda.nodes
for host in "${!redpandas[@]}"; do
  echo "${redpandas[$host]} ${node_ids[$host]}" >> /mnt/vectorized/redpanda.nodes
done
chown ubuntu:ubuntu /mnt/vectorized/redpanda.nodes

rm -rf /mnt/vectorized/client.nodes
client_node_id=0
for host in "${!clients[@]}"; do
  echo "${clients[$host]} $client_node_id" >> /mnt/vectorized/client.nodes
  ((client_node_id=client_node_id+1))
done
chown ubuntu:ubuntu /mnt/vectorized/client.nodes

rm -rf /home/ubuntu/.ssh/known_hosts
for host in "${!redpandas[@]}"; do
  until ssh-keyscan "${redpandas[$host]}" > /dev/null 2>&1; do
    >&2 echo "sshd on $host (${redpandas[$host]}) is unavailable - sleeping for 1s"
    sleep 1s
  done
  ssh-keyscan "${redpandas[$host]}" 2> /dev/null >> /home/ubuntu/.ssh/known_hosts
done

for host in "${!clients[@]}"; do
  until ssh-keyscan "${clients[$host]}" > /dev/null 2>&1; do
    >&2 echo "sshd on $host (${clients[$host]}) is unavailable - sleeping for 1s"
    sleep 1s
  done
  ssh-keyscan "${clients[$host]}" 2> /dev/null >> /home/ubuntu/.ssh/known_hosts
done
chown ubuntu:ubuntu /home/ubuntu/.ssh/known_hosts

touch /mnt/vectorized/ready

echo "Cluster is ready"

sleep infinity