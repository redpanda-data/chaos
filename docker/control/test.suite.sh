#!/usr/bin/env bash

set -e

MAX_ATTEMPS=30

suite_path="/mnt/vectorized/$1"
repeat=$2
now=$(date +%s)
rand_suffix=$(tr -dc A-Za-z0-9 </dev/urandom | head -c 7 | tr '[:upper:]' '[:lower:]')
run_id="${now}-${rand_suffix}"

if [ ! -f $suite_path ]; then
  echo "suite $suite_path doesn't exist"
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

echo >&1 "Running test suite $suite_path (run_id=${run_id})"
sudo -i -u ubuntu bash <<EOF
    python3 /mnt/vectorized/harness/test.suite.py --run_id $run_id --suite $suite_path --repeat $repeat
EOF

chmod -R o+rwx /mnt/vectorized/experiments
