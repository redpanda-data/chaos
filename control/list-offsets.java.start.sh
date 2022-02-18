#!/bin/bash

set -e

cd /mnt/vectorized/workloads/logs
nohup java -cp /mnt/vectorized/workloads/uber/target/uber-1.0-SNAPSHOT.jar:/mnt/vectorized/workloads/uber/target/dependency/* io.vectorized.list_offsets.App >/mnt/vectorized/workloads/logs/system.log 2>&1 &
echo $! >/mnt/vectorized/workloads/logs/list-offsets.pid
