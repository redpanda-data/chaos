#!/usr/bin/env bash

set -e

if [ "$COMPOSE_PROJECT_NAME" == "" ]; then
  echo "Please set COMPOSE_PROJECT_NAME environment variable"
  exit 1
fi

test_path=$1
repeat=$2

if [ "$repeat" == "" ]; then
  repeat="1"
fi

docker exec -it $COMPOSE_PROJECT_NAME-control /mnt/vectorized/test.test.sh $test_path $repeat
