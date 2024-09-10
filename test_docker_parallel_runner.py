import random
import time
import unittest
from unittest.mock import patch
import docker_parallel_runner
from docker_parallel_runner import Suite, UnschedulableSuitesError


class TestScheduler(unittest.TestCase):

    def test_zero_suites(self):
        succeeded_count, err_count = docker_parallel_runner.run_suites([], total_cpu_available=4)
        assert succeeded_count == 0
        assert err_count == 0

    def test_oversized_suite(self):
        with self.assertRaises(UnschedulableSuitesError):
            docker_parallel_runner.run_suites(
                [Suite("suite.json", 6, 2)],
                total_cpu_available=4)

    @patch('docker_parallel_runner.run_one')
    def test_suite_error(self, m_run_one):
        m_run_one.side_effect = lambda suite: (suite, RuntimeError("Docker rebuild error!"))
        succeeded_count, err_count = docker_parallel_runner.run_suites(
            [
                Suite("suite0.json", 4, 1),
                Suite("suite1.json", 4, 1),
                Suite("suite2.json", 4, 1),
                Suite("suite3.json", 4, 1),
                Suite("suite4.json", 4, 1),
            ],
            total_cpu_available=18)
        print(succeeded_count, err_count)
        assert succeeded_count == 0
        assert err_count == 1, "Scheduler loop should break out on first error"

    @patch('docker_parallel_runner.run_one')
    def test_randomized_suites(self, m_run_one):
        class FakeSuite(Suite):
            def __init__(self, *args, **kwargs):
                super(FakeSuite, self).__init__(*args, **kwargs)
                # [0, 2) cpus needed
                self._cpus_needed = 2 * random.random()
                # [0, 1) run duration
                self._run_duration = random.random()

            @property
            def cpus_needed(self):
                return self._cpus_needed

            @property
            def run_duration(self):
                return self._run_duration

            def __hash__(self):
                return id(self)

        suites_that_got_run = []

        cpu_used = 0.0

        total_cpu_available = 100

        def _fake_run_one(suite: FakeSuite):
            nonlocal cpu_used
            cpu_used += suite.cpus_needed
            assert cpu_used <= total_cpu_available
            time.sleep(suite.run_duration)
            suites_that_got_run.append(suite)
            cpu_used -= suite.cpus_needed
            return suite, None

        m_run_one.side_effect = _fake_run_one
        fake_suites = [FakeSuite(f"suite{i}.json", 1, 1) for i in range(2000)]

        t = time.time()
        succeeded_count, err_count = docker_parallel_runner.run_suites(fake_suites,
                                                                       total_cpu_available=total_cpu_available)
        total_duration = time.time() - t

        total_cpu_seconds_needed = sum(s.run_duration * s.cpus_needed for s in fake_suites)
        ideal_duration = total_cpu_seconds_needed / total_cpu_available
        assert succeeded_count == len(fake_suites)
        assert err_count == 0
        assert set(suites_that_got_run) == set(fake_suites)
        assert abs(cpu_used) < 0.05

        # This check is really a sanity check re: correctness. 20% is arbitrarily chosen, no supporting calculations
        assert total_duration / ideal_duration < 1.20, f"Total duration: {total_duration}, ideal duration: {ideal_duration} (wasted more than 20%)"


if __name__ == '__main__':
    unittest.main()
