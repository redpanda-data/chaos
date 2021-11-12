#!/bin/bash

set -e

cd /mnt/vectorized/workloads/logs
nohup java -cp /mnt/vectorized/workloads/writing/list-offsets/target/list-offsets-1.0-SNAPSHOT.jar:/mnt/vectorized/workloads/writing/list-offsets/target/dependency/* io.vectorized.App > /mnt/vectorized/workloads/logs/list-offsets.log 2>&1 & echo $! > /mnt/vectorized/workloads/logs/list-offsets.pid