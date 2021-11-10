Set `DEB_PATH` with path to the redpanda deb package (build redpanda with `task rp:build` then assemble .deb package with `task rp:build-pkg PKG_FORMATS=deb`; usually it is assembled to `vbuild/release/clang/dist/debian/redpanda_0.0-dev-0000000_amd64.deb`)

## Test on AWS (terraform & ansible)

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

    ./fetch.aws.logs.sh

Cleanup:

    terraform destroy

## Test locally (docker & docker-compose)

Build docker images:

    ./docker/rebuild.sh

Start local cluster:

    ./docker/up.sh

Run a specific test suite:

    ./docker/test.suite.sh test_suite_all.json

Run a specific test suite `n` times:

    ./docker/test.suite.sh test_suite_all.json n

Run a specific test:

    ./docker/test.test.sh writing_kafka_clients/kill_leader.json

Copy test & redpanda logs (find them in the `results` folder):

    ./fetch.docker.logs.sh