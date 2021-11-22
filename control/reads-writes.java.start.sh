#!/bin/bash

set -e

cd /mnt/vectorized/workloads/logs
nohup java -cp /mnt/vectorized/workloads/writing/reads-writes/target/reads-writes-1.0-SNAPSHOT.jar:/mnt/vectorized/workloads/writing/reads-writes/target/dependency/* io.vectorized.App > /mnt/vectorized/workloads/logs/reads-writes.log 2>&1 & echo $! > /mnt/vectorized/workloads/logs/reads-writes.pid