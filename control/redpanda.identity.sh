#!/bin/bash

set -e

id=$1
ip=$2
ips=$3

if [ "$ips" == "" ]; then
  rpk config bootstrap \
    --id $id \
    --self $ip
else
  rpk config bootstrap \
    --id $id \
    --self $ip \
    --ips $ips
fi
