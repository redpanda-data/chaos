#!/usr/bin/env bash

set -e

test_path=$1
repeat=$2

if [ "$repeat" == "" ]; then
    repeat="1"
fi

docker exec -it control /mnt/vectorized/test.test.sh $test_path $repeat