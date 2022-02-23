#!/usr/bin/env bash

set -e

test_path="/mnt/vectorized/suites/tests/$1"
repeat=$2
now=$(date +%s)

if [ ! -f $test_path ]; then
  echo "test $test_path doesn't exist"
  exit 1
fi

if [ "$repeat" == "" ]; then
  repeat="1"
fi

until [ -f /mnt/vectorized/ready ]; do
  echo >&2 "control node isn't fully initialized; sleeping for 1s"
  sleep 1s
done

sudo -i -u ubuntu bash <<EOF
    python3 /mnt/vectorized/harness/test.test.py --run_id $now --test $test_path --repeat $repeat
EOF

chmod -R o+rwx /mnt/vectorized/experiments
