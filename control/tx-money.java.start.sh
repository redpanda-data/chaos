#!/bin/bash

set -e

cd /mnt/vectorized/workloads/logs
nohup java -cp /mnt/vectorized/workloads/tx-money/target/tx-money-1.0-SNAPSHOT.jar:/mnt/vectorized/workloads/tx-money/target/dependency/* io.vectorized.App > /mnt/vectorized/workloads/logs/tx-money.log 2>&1 & echo $! > /mnt/vectorized/workloads/logs/tx-money.pid