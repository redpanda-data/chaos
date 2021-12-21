#!/bin/bash

set -e

cd /mnt/vectorized/workloads/logs
nohup java -cp /mnt/vectorized/workloads/tx-subscribe/target/tx-subscribe-1.0-SNAPSHOT.jar:/mnt/vectorized/workloads/tx-subscribe/target/dependency/* io.vectorized.App > /mnt/vectorized/workloads/logs/tx-subscribe.log 2>&1 & echo $! > /mnt/vectorized/workloads/logs/tx-subscribe.pid