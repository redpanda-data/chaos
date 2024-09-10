#!/usr/bin/env python3
import argparse
import dataclasses
import logging
import re
import shlex
import subprocess
import time
from concurrent.futures import Future, ThreadPoolExecutor, as_completed
from typing import List, Tuple, Optional, Sequence

import os


def main():
    parser = argparse.ArgumentParser(
        description="Run test suites in parallel in docker. Includes full Docker setup / teardown per suite")
    parser.add_argument("--suite", dest="suite_strs", action='append',
                        help="Run suites of the form TEST_SUITE_JSON:RP_CLUSTER_SIZE:CLIENT_COUNT. "
                             f"Possible (RP_CLUSTER_SIZE, CLIENT_COUNT) values: {POSSIBLE_SIZE_COMBOS}. "
                             "May provide multiple.")
    parser.add_argument("--core-count-mult",
                        type=float,
                        default=1.0,
                        help="Tweak parallelism by scaling effective core count")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s docker_parallel_runner.py %(levelname)s %(message)s"
    )

    # For x86, we are counting hyperthreads as cpu cores for simplicity.
    # In CI:
    # - x86 hosts run with 48 "hyperthread" cores
    # - ARM hosts run with 48 "real" cores
    # Even though Hyperthreads weaker than "real" cores, in practice they still seem to work fine
    # when we allocate 1 of them to container.
    #
    # TODO: Can 48 core ARM hosts run even more than 48 containers then?
    actual_cpu_available = os.cpu_count()
    assert actual_cpu_available, "Could not determine available cpu count on system"
    logging.info(f"Actual total CPU available on system: {actual_cpu_available}")
    total_cpu_available = float(actual_cpu_available * args.core_count_mult)
    logging.info(f"Effective CPU available (core_count_mult={args.core_count_mult}): {total_cpu_available}")

    suites = get_suites(args.suite_strs)
    logging.info(f"Got test suites: {suites}")

    logging.info(
        "Generating SSH key (if none exists). "
        "Used by all test suites, so do it once at beginning to avoid race."
    )
    generate_ssh_key()
    success_count, err_count = run_suites(suites, total_cpu_available=total_cpu_available)
    if success_count != len(suites):
        logging.error(
            f"Failed to run all ({len(suites)}) suites successfully. Succeeded: {success_count}, Error: {err_count}")
        exit(1)


@dataclasses.dataclass
class Suite:
    """What test suite to run, and with what cluster size"""
    suite_file: str  # Should look like a JSON file. E.g. "test_suite_1.json"
    rp_cluster_size: int
    client_count: int

    @property
    def docker_compose_project_name(self) -> str:
        m = re.search(r"^([a-z0-9][a-z0-9_-]*).*", os.path.basename(self.suite_file))
        if m is None:
            raise ValueError(
                f"Invalid test suite: {self.suite_file}. "
                "The path's basename should conform to COMPOSE_PROJECT_NAME format. "
                "See https://docs.docker.com/compose/project-name/#set-a-project-name")
        return m.group(1)

    @property
    def cpus_needed(self) -> float:
        # What uses CPU in a test suite?
        # - RP broker containers
        # - client containers
        # - control container (there is always just 1)
        # This formula assumes 1 CPU per container
        return float(self.rp_cluster_size + self.client_count + 1)

    def __str__(self):
        return repr(self)


def generate_ssh_key():
    # ssh key will be used to connect to the control container
    # add a timeout - since ssh-keygen can hang waiting for user input (e.g. "Overwrite (y/n)?")
    if os.path.exists("id_ed25519"):
        logging.info("SSH key already exists. Skipping generation.")
        return
    cmd = ["ssh-keygen", "-t", "ed25519", "-f", "id_ed25519", "-N", ""]
    logging.info(f"Running command: {' '.join(shlex.quote(arg) for arg in cmd)}")
    subprocess.check_call(cmd, timeout=10)


class SuiteRunner:
    def __init__(self,
                 rebuild_script: str,
                 up_script: str,
                 ready_script: str,
                 down_script: str,
                 fetch_logs_script: str,
                 test_suite_script: str,
                 docker_compose_project_name: str):
        self._rebuild_script = rebuild_script
        self._up_script = up_script
        self._ready_script = ready_script
        self._down_script = down_script
        self._fetch_logs_script = fetch_logs_script
        self._test_suite_script = test_suite_script
        self._docker_compose_project_name = docker_compose_project_name

    def _run(self, cmd: List[str], extra_env: dict = {}):
        logging.info(f"Running command: {' '.join(shlex.quote(arg) for arg in cmd)}")
        if "COMPOSE_PROJECT_NAME" in os.environ:
            raise EnvironmentError(
                "COMPOSE_PROJECT_NAME is already set in initial environment - but this script will set its own!")
        subprocess.check_call(cmd, env={
            **os.environ,
            **extra_env,
            "COMPOSE_PROJECT_NAME":
                self._docker_compose_project_name})

    def rebuild(self):
        # Rebuild scripts by default will generate an SSH key at a fixed common location
        # We want to skip this step, as rebuild may be happening across concurrent suites.
        # Instead we will prepare the SSH key once before starting any suites.
        return self._run([self._rebuild_script],
                         extra_env={"SKIP_SSH_KEYGEN": "1"})

    def up(self):
        return self._run([self._up_script])

    def wait_ready(self):
        return self._run([self._ready_script])

    def down(self):
        return self._run([self._down_script])

    def fetch_logs(self):
        return self._run([self._fetch_logs_script])

    def run_test_suite(self, test_suite: str):
        return self._run([self._test_suite_script, test_suite])


def get_suites(suite_strs: Tuple[str]) -> List[Suite]:
    suites = []

    # These are used for checking for duplicates
    suite_files = set()
    docker_compose_project_names = set()

    for suite_str in suite_strs:
        logging.info(f"Parsing suite str '{suite_str}'")
        try:
            # E.g. "suites/test_something.json:6:2"
            test_suite, rp_cluster_size, client_count = suite_str.split(":")
            rp_cluster_size = int(rp_cluster_size)
            client_count = int(client_count)
        except Exception:
            raise ValueError(f"Invalid suite: {suite_str}")

        if (rp_cluster_size, client_count) not in POSSIBLE_SIZE_COMBOS:
            # Underlying bash scripts literally only support these three combos.
            # Hence, we explicitly error out on bad input early.
            raise ValueError(f"Invalid cluster size, client count: ({rp_cluster_size}, {client_count})")

        suite = Suite(suite_file=test_suite,
                      rp_cluster_size=rp_cluster_size, client_count=client_count)

        if suite.suite_file in suite_files:
            raise ValueError(f"Duplicate test suite: {suite.suite_file}")
        suite_files.add(suite.suite_file)

        if not os.path.exists(suite.suite_file):
            raise ValueError(f"Test suite file not found: {suite.suite_file}")

        if suite.docker_compose_project_name in docker_compose_project_names:
            raise ValueError(f"Duplicate docker-compose project name: {suite.docker_compose_project_name}")
        docker_compose_project_names.add(suite.docker_compose_project_name)

        suites.append(suite)
    return suites


class UnschedulableSuitesError(Exception):
    pass


def run_suites(suites: Sequence[Suite], total_cpu_available: float) -> Tuple[int, int]:
    # We implement our own scheduling based on CPU availability
    # We leverage the ThreadPoolExecutor for its simple threading interface
    # Therefore we effectively do not constrain on max_workers (set to theoretical max usage == len(suites))
    executor = ThreadPoolExecutor(max_workers=len(suites) or None)

    current_cpu_available = total_cpu_available

    running_futures: List[Future] = []
    succeeded_count = 0
    error_count = 0

    # sort suites by CPU requirement, descending
    suites_pending_submission = sorted(suites, key=lambda s: s.cpus_needed, reverse=True)

    # Keep going, if either there are things to submit, or things are running (and need to be waited on)
    while suites_pending_submission or running_futures:
        if error_count > 0:
            logging.error(
                f"SOMETHING ERROR'D OUT - NOT STARTING ANY MORE SUITES (remaining: {suites_pending_submission})")
            break

        # eagerly submit as many suites as possible
        # chunkiest first, no lookahead
        submitted_suites: List[Suite] = []
        for s in suites_pending_submission:
            if s.cpus_needed <= current_cpu_available:
                logging.info(f"STARTING {s}")
                running_futures.append(executor.submit(run_one, s))
                current_cpu_available -= s.cpus_needed
                submitted_suites.append(s)
                logging.info(f"Something submitted: CPU available={current_cpu_available}")
                logging.info(f"Currently running {len(running_futures)} suites")

        if not running_futures and not submitted_suites:
            assert abs(current_cpu_available - total_cpu_available) < 0.1, \
                (f"When nothing is running, current_cpu_available should be equal to total_cpu_available. "
                 f"({current_cpu_available} vs {total_cpu_available})")
            logging.error(f"No progress can be made with these remaining suites: {suites_pending_submission}")
            raise UnschedulableSuitesError("Unschedulable suites")

        # remove the just submitted suites from pending
        for s in submitted_suites:
            suites_pending_submission.remove(s)

        try:
            # wait for any one suite to complete
            # main thread will spend most of its time here
            completed_future = next(as_completed(running_futures))
        except StopIteration:
            # no more futures to wait on, start another submit/wait cycle
            continue

        # remove the completed future from running futures
        running_futures.remove(completed_future)

        # free up CPU budget
        completed_suite, exc = completed_future.result()
        current_cpu_available += completed_suite.cpus_needed
        if exc:
            logging.error(f"Error when running suite {completed_suite.suite_file}) - {exc}")
            logging.info(f"ERRORED {completed_suite.suite_file}")
            error_count += 1
        else:
            logging.info(f"SUCCEEDED {completed_suite.suite_file}")
            succeeded_count += 1

        logging.info(f"    (TOTAL, SUCCEEDED, ERROR) = {len(suites), succeeded_count, error_count}")
        logging.info(f"Something completed: CPU available={current_cpu_available}")
    return succeeded_count, error_count


POSSIBLE_SIZE_COMBOS = (
    (4, 1),
    (6, 1),
    (6, 2),
)


def get_suite_runner(docker_compose_project_name: str, rp_cluster_size: int, client_count: int) -> SuiteRunner:
    if (rp_cluster_size, client_count) == (4, 1):
        return SuiteRunner(
            rebuild_script="./docker/rebuild4.sh",
            up_script="./docker/up4.sh",
            ready_script="./docker/ready4.sh",
            down_script="./docker/down4.sh",
            fetch_logs_script="./docker/fetch.logs.sh",
            test_suite_script="./docker/test.suite.sh",
            docker_compose_project_name=docker_compose_project_name,
        )
    elif (rp_cluster_size, client_count) == (6, 1):
        return SuiteRunner(
            rebuild_script="./docker/rebuild6.sh",
            up_script="./docker/up6.sh",
            ready_script="./docker/ready6.sh",
            down_script="./docker/down6.sh",
            fetch_logs_script="./docker/fetch.logs.sh",
            test_suite_script="./docker/test.suite.sh",
            docker_compose_project_name=docker_compose_project_name,
        )
    elif (rp_cluster_size, client_count) == (6, 2):
        return SuiteRunner(
            rebuild_script="./docker/rebuild6.2.sh",
            up_script="./docker/up6.2.sh",
            ready_script="./docker/ready6.2.sh",
            down_script="./docker/down6.2.sh",
            fetch_logs_script="./docker/fetch.logs.sh",
            test_suite_script="./docker/test.suite.sh",
            docker_compose_project_name=docker_compose_project_name,
        )
    else:
        raise ValueError(f"Invalid cluster size / client count: ({rp_cluster_size}, {client_count})")


def run_one(suite: Suite) -> Tuple[Suite, Optional[Exception]]:
    t = time.time()
    try:
        runner = get_suite_runner(suite.docker_compose_project_name, suite.rp_cluster_size, suite.client_count)

        runner.rebuild()
        runner.up()

        try:
            runner.wait_ready()
        except Exception:
            logging.info("Cluster did not reach ready state")
            runner.down()
            raise Exception("Cluster did not reach ready state")

        runner.run_test_suite(suite.suite_file)
        runner.fetch_logs()
        runner.down()

        return suite, None
    except Exception as e:
        return suite, e
    finally:
        # "Completed" does not mean "succeeded"!
        logging.info(f"Completed suite {suite.suite_file} in {time.time() - t} seconds")


if __name__ == '__main__':
    main()
