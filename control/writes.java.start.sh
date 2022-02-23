#!/bin/bash

set -e

cd /mnt/vectorized/workloads/logs
nohup java -cp /mnt/vectorized/workloads/writes/kafka-clients/target/kafka-clients-1.0-SNAPSHOT.jar:/mnt/vectorized/workloads/writes/kafka-clients/target/dependency/* io.vectorized.App >/mnt/vectorized/workloads/logs/system.log 2>&1 &
echo $! >/mnt/vectorized/workloads/logs/kafka-clients.pid
