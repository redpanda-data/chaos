import os
import yaml
import logging.config
import logging
import time
import json
import argparse
import sys
import traceback
from sh import mkdir
from logging import FileHandler, Formatter
from chaos.checks.result import Result
from chaos.scenarios.all import SCENARIOS

with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "log.yaml"), 'rt') as f:
    try:
        config = yaml.safe_load(f.read())
        logging.config.dictConfig(config)
    except Exception as e:
        print(e)
        logging.basicConfig(level=logging.INFO)

parser = argparse.ArgumentParser(description='kafka-clients chaos runner')
parser.add_argument('--suite', required=True)
parser.add_argument('--repeat', type=int, default=1, required=False)
parser.add_argument('--run_id', required=True)
args = parser.parse_args()

chaos_logger = logging.getLogger("chaos")
tasks_logger = logging.getLogger("tasks")
formatter = Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

suite = None
with open(args.suite, "r") as suite_file:
    suite = json.load(suite_file)

if "settings" not in suite:
    suite["settings"] = {
        "test": {},
        "suite": {}
    }

tests = {}
ignore_transient_errors = False
at_least_one_passes = False
should_retry_on_transient_errors = False

if "ignore_transient_errors" in suite["settings"]["suite"]:
    ignore_transient_errors = suite["settings"]["suite"]["ignore_transient_errors"]

if "at_least_one_passes" in suite["settings"]["suite"]:
    at_least_one_passes = suite["settings"]["suite"]["at_least_one_passes"]

retries = 0
if "should_retry_on_transient_errors" in suite["settings"]["suite"]:
    should_retry_on_transient_errors = suite["settings"]["suite"]["should_retry_on_transient_errors"]
    if should_retry_on_transient_errors:
        if ignore_transient_errors:
            raise Exception(f"ignore_transient_errors isn't compatible with should_retry_on_transient_errors")
        if at_least_one_passes:
            raise Exception(f"at_least_one_passes isn't compatible with should_retry_on_transient_errors")
        if "retries" in suite["settings"]["suite"]:
            retries = suite["settings"]["suite"]["retries"]
        else:
            raise Exception(f"retry should be provided when should_retry_on_transient_errors")

for test_path in suite["tests"]:
    test_path = os.path.join(os.path.dirname(args.suite), "tests", test_path)
    test = None
    with open(test_path, "r") as test_file:
        test = json.load(test_file)
    if test["name"] in tests:
        raise Exception(f"test name must be unique {test['name']} has a duplicate")
    if test["scenario"] not in SCENARIOS:
        raise Exception(f"unknown scenario: {test['scenario']}")
    if "settings" not in test:
        test["settings"] = {}
    for key in suite["settings"]["test"].keys():
        test["settings"][key] = suite["settings"]["test"][key]
    
    scenario = SCENARIOS[test["scenario"]]()
    scenario.validate(test)
    tests[test["name"]] = test

results = {
    "test_runs": {},
    "name": suite["name"],
    "result": Result.PASSED,
    "run_id": args.run_id
}

for i in range(0, args.repeat):
    most_severe_result = Result.PASSED
    least_severe_result = Result.FAILED
    for name in tests:
        if name not in results["test_runs"]:
            results["test_runs"][name] = {}
        
        attempt = 0
        passed = True
        while attempt <= retries:
            attempt += 1
            experiment_id = str(int(time.time()))

            mkdir("-p", f"/mnt/vectorized/experiments/{experiment_id}")
            handler = FileHandler(f"/mnt/vectorized/experiments/{experiment_id}/log")
            handler.setFormatter(formatter)
            chaos_logger.addHandler(handler)
            tasks_logger.addHandler(handler)
            
            test = tests[name]
            try:
                scenario = SCENARIOS[test["scenario"]]()
                description = scenario.execute(test, experiment_id)
                results["test_runs"][test["name"]][experiment_id] = description["result"]
            except:
                chaos_logger.exception("error on running an experiment")
                results["test_runs"][test["name"]][experiment_id] = Result.UNKNOWN
            finally:
                handler.flush()
                handler.close()
                chaos_logger.removeHandler(handler)
                tasks_logger.removeHandler(handler)
            
            if results["test_runs"][test["name"]][experiment_id] == Result.FAILED:
                passed = False
                break

            with open(f"/mnt/vectorized/experiments/{args.run_id}.json", "w") as info:
                info.write(json.dumps(results, indent=2))
            with open(f"/mnt/vectorized/experiments/latest.json", "w") as info:
                info.write(json.dumps(results, indent=2))
            
            if should_retry_on_transient_errors:
                passed = results["test_runs"][test["name"]][experiment_id] == Result.PASSED
            else:
                most_severe_result = Result.more_severe(most_severe_result, results["test_runs"][test["name"]][experiment_id])
                least_severe_result = Result.least_severe(least_severe_result, results["test_runs"][test["name"]][experiment_id])
            
            if passed:
                break
        
        if not passed:
            results["result"] = Result.FAILED
            with open(f"/mnt/vectorized/experiments/{args.run_id}.json", "w") as info:
                info.write(json.dumps(results, indent=2))
            with open(f"/mnt/vectorized/experiments/latest.json", "w") as info:
                info.write(json.dumps(results, indent=2))


    if not(should_retry_on_transient_errors):
        if most_severe_result == Result.FAILED:
            least_severe_result = Result.FAILED
        if ignore_transient_errors:
            if at_least_one_passes:
                results["result"] = Result.more_severe(results["result"], least_severe_result)
            elif least_severe_result == Result.FAILED:
                results["result"] = Result.FAILED
        else:
            results["result"] = Result.more_severe(results["result"], most_severe_result)
    
    with open(f"/mnt/vectorized/experiments/{args.run_id}.json", "w") as info:
        info.write(json.dumps(results, indent=2))
    with open(f"/mnt/vectorized/experiments/latest.json", "w") as info:
        info.write(json.dumps(results, indent=2))