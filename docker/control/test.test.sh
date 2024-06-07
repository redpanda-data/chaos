#!/usr/bin/env bash

set -e

MAX_ATTEMPS=30

test_path="/mnt/vectorized/$1"
repeat=$2
now=$(date +%s)

if [ ! -f $test_path ]; then
  echo "test $test_path doesn't exist"
  exit 1
fi

if [ "$repeat" == "" ]; then
  repeat="1"
fi

attempt=0
until [ -f /mnt/vectorized/ready ]; do
  echo >&2 "control node isn't fully initialized; sleeping for 1s"
  sleep 1s
  ((attempt = attempt + 1))
  if [[ $attempt -eq $MAX_ATTEMPS ]]; then
    echo "cluster isn't ready"
    exit 1
  fi
done

sudo -i -u ubuntu bash <<EOF
    python3 /mnt/vectorized/harness/test.test.py --run_id $now --test $test_path --repeat $repeat
EOF

chmod -R o+rwx /mnt/vectorized/experiments
