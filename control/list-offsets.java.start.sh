#!/bin/bash

set -e

cd /mnt/vectorized/workloads/logs
nohup java -cp /mnt/vectorized/workloads/list-offsets/target/list-offsets-1.0-SNAPSHOT.jar:/mnt/vectorized/workloads/list-offsets/target/dependency/* io.vectorized.App >/mnt/vectorized/workloads/logs/system.log 2>&1 &
echo $! >/mnt/vectorized/workloads/logs/list-offsets.pid
