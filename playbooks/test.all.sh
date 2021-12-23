#!/usr/bin/env bash

set -e

if [ "$AWS_CHAOS_RESOURCE_PREFIX" == "" ]; then
    echo "set AWS_CHAOS_RESOURCE_PREFIX to distinguish aws resources between users"
    exit 1
fi

terraform apply -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=6" -var="workload_cluster_size=2" -auto-approve
sleep 1m
ansible-playbook deploy.yml
ansible-playbook playbooks/test.suite.yml -e suite_path=test_suite_tx_subscribe.json
./playbooks/fetch.logs.sh
terraform destroy -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=6" -var="workload_cluster_size=2" -auto-approve

terraform apply -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=6" -var="workload_cluster_size=1" -auto-approve
sleep 1m
ansible-playbook deploy.yml
ansible-playbook playbooks/test.suite.yml -e suite_path=test_suite_tx_money.json
ansible-playbook playbooks/test.suite.yml -e suite_path=test_suite_tx_reads_writes.json
ansible-playbook playbooks/test.suite.yml -e suite_path=test_suite_tx_streaming.json
./playbooks/fetch.logs.sh
terraform destroy -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=6" -var="workload_cluster_size=1" -auto-approve

terraform apply -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=3" -var="workload_cluster_size=1" -auto-approve
sleep 1m
ansible-playbook deploy.yml
ansible-playbook playbooks/test.suite.yml -e suite_path=test_suite_reads_writes.json
ansible-playbook playbooks/test.suite.yml -e suite_path=test_suite_list_offsets.json
ansible-playbook playbooks/test.suite.yml -e suite_path=test_suite_idempotency.json
./playbooks/fetch.logs.sh
terraform destroy -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=3" -var="workload_cluster_size=1" -auto-approve