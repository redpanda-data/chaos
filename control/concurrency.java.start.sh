#!/bin/bash

set -e

cd /mnt/vectorized/workloads/logs
nohup java -cp /mnt/vectorized/workloads/writes/concurrency/target/concurrency-1.0-SNAPSHOT.jar:/mnt/vectorized/workloads/writes/concurrency/target/dependency/* io.vectorized.App > /mnt/vectorized/workloads/logs/concurrency.log 2>&1 & echo $! > /mnt/vectorized/workloads/logs/concurrency.pid