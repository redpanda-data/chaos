# How to use chaos testing

Create a directory `DEB_DIR` to house required deb packages. `DEB_DIR` must be set in environment
when chaos tests are started.

Example:
```
export DEB_DIR=/var/tmp/my_chaos_debs/
mkdir $DEB_DIR
```

Place Redpanda .deb files into /var/tmp/my_chaos_deb/.

For the latest Redpanda versions, there should be:
* `$DEB_DIR/redpanda.deb`
* `$DEB_DIR/redpanda-tuner.deb`
* `$DEB_DIR/redpanda-rpk.deb`

Also set `DEB_FILE_LIST` variable to the list of deb files in `DEB_DIR`, in the desired install (`dpkg -i`) order.

It should be a quoted, space delimited string.

Example:
```
export DEB_FILE_LIST="redpanda-rpk.deb redpanda-tuner.deb redpanda.deb"
```

## Test locally (docker & docker-compose)

Requirements:
    - docker
    - docker-compose
    - python3

Don't forget to add current user to docker group: https://docs.docker.com/engine/install/linux-postinstall

### All in one (with docker-compose)

Run all tests with a single command:

    ./docker/test.all.sh

### Fine granularity

Or use individual commands for fine granularity.

Build docker images:

    ./docker/rebuild3.sh

Start local cluster:

    ./docker/up3.sh

Run a specific test suite:

    ./docker/test.suite.sh suites/test_suite_reads_writes.json

Run a specific test suite `n` times, e.g. three times:

    ./docker/test.suite.sh suites/test_suite_reads_writes.json 3

Run a specific test:

    ./docker/test.test.sh suites/tests/reads_writes/pause_leader.json

Copy test & redpanda logs (find them in the `results` folder):

    ./docker/fetch.logs.sh

# Dev help

 - [example](https://github.com/vectorizedio/chaos/pull/1) of adding new workload (writing sub-workflow)
 - [example](https://github.com/vectorizedio/chaos/pull/1) of adding new fault injection

## Test on AWS (terraform & ansible)

Install terraform and ansible:

  - https://learn.hashicorp.com/tutorials/terraform/install-cli
  - https://docs.ansible.com/ansible/latest/installation_guide/intro_installation.html#installing-ansible-on-ubuntu

Provision redpanda nodes, client & control node:

    terraform apply

Deploy redpanda & test harness:

    ansible-playbook deploy.yml --key-file=./id_ed25519

Run a default test suite (`suites/test_suite_all.json`):

    ansible-playbook playbooks/test.suite.yml --key-file=./id_ed25519

Run a default test suite `n` times:

    ansible-playbook playbooks/test.suite.yml -e repeat=n --key-file=./id_ed25519

Run a specific test suite:

    ansible-playbook playbooks/test.suite.yml -e suite_path=test_suite_all.json --key-file=./id_ed25519

Run a specific test:

    ansible-playbook playbooks/test.test.yml -e test_path=writing_kafka_clients/kill_leader.json --key-file=./id_ed25519

Copy test & redpanda logs (find them in the `results` folder):

    ./playbooks/fetch.logs.sh

Cleanup:

    terraform destroy