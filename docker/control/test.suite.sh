#!/usr/bin/env bash

set -e

suite_path="/mnt/vectorized/suites/$1"
repeat=$2
now=$(date +%s)

if [ ! -f $suite_path ]; then
    echo "suite $suite_path doesn't exist"
    exit 1
fi

if [ "$repeat" == "" ]; then
    repeat="1"
fi

until [ -f /mnt/vectorized/ready ]; do
    >&2 echo "control node isn't fully initialized; sleeping for 1s"
    sleep 1s
done

sudo -i -u ubuntu bash << EOF
    python3 /mnt/vectorized/harness/test.suite.py --run_id $now --suite $suite_path --repeat $repeat
EOF

chmod -R o+rwx /mnt/vectorized/experiments