#!/usr/bin/env bash

set -e

ansible-playbook playbooks/download.yml
find playbooks/experiments | grep tar | xargs -L 1 tar -xzf
rm -rf playbooks/experiments
mkdir -p results
cp -r mnt/vectorized/experiments/* results/
rm -rf mnt