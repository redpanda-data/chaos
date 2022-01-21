#!/bin/bash

set -e

cd /mnt/vectorized/workloads/logs
nohup java -cp /mnt/vectorized/workloads/tx-streaming/target/tx-streaming-1.0-SNAPSHOT.jar:/mnt/vectorized/workloads/tx-streaming/target/dependency/* io.vectorized.App > /mnt/vectorized/workloads/logs/system.log 2>&1 & echo $! > /mnt/vectorized/workloads/logs/tx-streaming.pid