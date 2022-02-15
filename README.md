# How to use chaos testing

Set `DEB_PATH` with path to the redpanda deb package, e.g.

```
export DEB_PATH="$HOME/redpanda_21.11.5-1-af88fa16_amd64.deb"
```

## Test on AWS (terraform & ansible)

Install terraform and ansible:

  - https://learn.hashicorp.com/tutorials/terraform/install-cli
  - https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html#installing-ansible-on-ubuntu

Provision redpanda nodes, client & control node:

    terraform apply

Deploy redpanda & test harness:

    ansible-playbook deploy.yml

Run a default test suite (`suites/test_suite_all.json`):

    ansible-playbook playbooks/test.suite.yml

Run a default test suite `n` times:

    ansible-playbook playbooks/test.suite.yml -e repeat=n

Run a specific test suite:

    ansible-playbook playbooks/test.suite.yml -e suite_path=test_suite_all.json

Run a specific test:

    ansible-playbook playbooks/test.test.yml -e test_path=writing_kafka_clients/kill_leader.json

Copy test & redpanda logs (find them in the `results` folder):

    ./playbooks/fetch.logs.sh

Cleanup:

    terraform destroy

## Test locally (docker & docker-compose)

Requirements:
    - docker
    - docker-compose
    - python3

Don't forget to add current user to docker group: https://docs.docker.com/engine/install/linux-postinstall

### All in one

Run all tests with a single command:

    ./docker/test.all.sh

### Fine granularity

Or use individual commands for fine granularity.

Build docker images:

    ./docker/rebuild3.sh

Start local cluster:

    ./docker/up3.sh

Run a specific test suite:

    ./docker/test.suite.sh test_suite_all.json

Run a specific test suite `n` times:

    ./docker/test.suite.sh test_suite_all.json n

Run a specific test:

    ./docker/test.test.sh reads_writes/pause_leader.json

Copy test & redpanda logs (find them in the `results` folder):

    ./docker/fetch.logs.sh

# Dev help

 - [example](https://github.com/vectorizedio/chaos/pull/1) of adding new workload (writing sub-workflow)
 - [example](https://github.com/vectorizedio/chaos/pull/1) of adding new fault injection