#!/usr/bin/env bash

set -e

for ip in "$@"; do
  sudo iptables -D INPUT -s $ip -j DROP
  sudo iptables -D OUTPUT -d $ip -j DROP
done
