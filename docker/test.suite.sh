#!/usr/bin/env bash

set -e

suite_path=$1
repeat=$2

if [ "$repeat" == "" ]; then
  repeat="1"
fi

docker exec -it control /mnt/vectorized/test.suite.sh $suite_path $repeat
