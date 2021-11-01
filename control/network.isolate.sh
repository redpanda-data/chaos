#!/usr/bin/env bash

set -e

for ip in "$@"; do
  sudo iptables -A INPUT -s $ip -j DROP
  sudo iptables -A OUTPUT -d $ip -j DROP
done
