#!/usr/bin/env bash

set -e

if [ "$AWS_CHAOS_RESOURCE_PREFIX" == "" ]; then
  echo "set AWS_CHAOS_RESOURCE_PREFIX to distinguish aws resources between users"
  exit 1
fi

if [ ! -f id_ed25519 ]; then
  ssh-keygen -t ed25519 -f id_ed25519 -N ""
fi

terraform apply -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=3" -var="workload_cluster_size=1" -auto-approve
sleep 1m
ansible-playbook deploy.yml --key-file id_ed25519
ansible-playbook playbooks/test.suite.yml --key-file id_ed25519 -e suite_path=test_suite_reads_writes.json
ansible-playbook playbooks/test.suite.yml --key-file id_ed25519 -e suite_path=test_suite_list_offsets.json
ansible-playbook playbooks/test.suite.yml --key-file id_ed25519 -e suite_path=test_suite_idempotency.json
./playbooks/fetch.logs.sh
terraform destroy -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=3" -var="workload_cluster_size=1" -auto-approve

terraform apply -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=6" -var="workload_cluster_size=2" -auto-approve
sleep 1m
ansible-playbook deploy.yml --key-file id_ed25519
ansible-playbook playbooks/test.suite.yml --key-file id_ed25519 -e suite_path=test_suite_tx_subscribe_1.json
ansible-playbook playbooks/test.suite.yml --key-file id_ed25519 -e suite_path=test_suite_tx_subscribe_2.json
ansible-playbook playbooks/test.suite.yml --key-file id_ed25519 -e suite_path=test_suite_tx_subscribe_3.json
./playbooks/fetch.logs.sh
terraform destroy -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=6" -var="workload_cluster_size=2" -auto-approve

terraform apply -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=6" -var="workload_cluster_size=1" -auto-approve
sleep 1m
ansible-playbook deploy.yml --key-file id_ed25519
ansible-playbook playbooks/test.suite.yml --key-file id_ed25519 -e suite_path=test_suite_tx_money.json
ansible-playbook playbooks/test.suite.yml --key-file id_ed25519 -e suite_path=test_suite_tx_reads_writes.json
ansible-playbook playbooks/test.suite.yml --key-file id_ed25519 -e suite_path=test_suite_reads_writes_decommission.json
./playbooks/fetch.logs.sh
terraform destroy -var="username=$AWS_CHAOS_RESOURCE_PREFIX" -var="redpanda_cluster_size=6" -var="workload_cluster_size=1" -auto-approve
