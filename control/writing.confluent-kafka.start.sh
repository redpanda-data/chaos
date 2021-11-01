#!/bin/bash

set -e

cd /mnt/vectorized/workloads/logs
nohup python3 /mnt/vectorized/workloads/writing/confluent-kafka/app.py > /mnt/vectorized/workloads/logs/confluent-kafka.log 2>&1 & echo $! > /mnt/vectorized/workloads/logs/confluent-kafka.pid