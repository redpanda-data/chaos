#!/usr/bin/env bash

declare -A ids=( ["redpanda1"]="0" ["redpanda2"]="1" ["redpanda3"]="2")
for name in "${!ids[@]}"; do
  ip=$(getent hosts $name | awk '{ print $1 }')
  ssh-keyscan $ip >> /home/ubuntu/.ssh/known_hosts
done

ip=$(getent hosts client1 | awk '{ print $1 }')
ssh-keyscan $ip >> /home/ubuntu/.ssh/known_hosts

chown ubuntu:ubuntu /home/ubuntu/.ssh/known_hosts