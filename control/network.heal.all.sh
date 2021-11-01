#!/usr/bin/env bash

set -e

for ip in $(cat /mnt/vectorized/redpanda.nodes | awk '{print $1}'); do
  if sudo iptables -C INPUT -s $ip -j DROP; then
    sudo iptables -D INPUT -s $ip -j DROP
  fi
  if sudo iptables -C OUTPUT -d $ip -j DROP; then
    sudo iptables -D OUTPUT -d $ip -j DROP
  fi
done