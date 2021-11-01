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

sudo -i -u ubuntu bash << EOF
    if [ ! -f /home/ubuntu/.ssh/known_hosts ]; then
        . /mnt/vectorized/known_hosts.sh
    fi

    python3 /mnt/vectorized/harness/test.suite.py --run_id $now --suite $suite_path --repeat $repeat
EOF

chmod -R o+rwx /mnt/vectorized/experiments