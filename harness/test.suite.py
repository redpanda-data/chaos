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

logger = logging.getLogger("chaos")
formatter = Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

suite = None
with open(args.suite, "r") as suite_file:
    suite = json.load(suite_file)

if "settings" not in suite:
    suite["settings"] = {}

tests = {}

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
    for key in suite["settings"].keys():
        test["settings"][key] = suite["settings"][key]
    
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
    for name in tests:
        if name not in results["test_runs"]:
            results["test_runs"][name] = {}
        
        experiment_id = str(int(time.time()))

        mkdir("-p", f"/mnt/vectorized/experiments/{experiment_id}")
        handler = FileHandler(f"/mnt/vectorized/experiments/{experiment_id}/log")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
        test = tests[name]
        try:
            scenario = SCENARIOS[test["scenario"]]()
            description = scenario.execute(test, experiment_id)
            results["test_runs"][test["name"]][experiment_id] = description["result"]
        except:
            e, v = sys.exc_info()[:2]
            trace = traceback.format_exc()
            logger.error(v)
            logger.error(trace)
            results["test_runs"][test["name"]][experiment_id] = "UNKNOWN"
        finally:
            handler.flush()
            handler.close()
            logger.removeHandler(handler)
        results["result"] = Result.more_severe(results["result"], results["test_runs"][test["name"]][experiment_id])

        with open(f"/mnt/vectorized/experiments/{args.run_id}.json", "w") as info:
            info.write(json.dumps(results, indent=2))
        with open(f"/mnt/vectorized/experiments/latest.json", "w") as info:
            info.write(json.dumps(results, indent=2))