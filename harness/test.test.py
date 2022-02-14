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
parser.add_argument('--test', required=True)
parser.add_argument('--repeat', type=int, default=1, required=False)
parser.add_argument('--run_id', required=True)
args = parser.parse_args()

chaos_logger = logging.getLogger("chaos")
tasks_logger = logging.getLogger("tasks")
formatter = Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")

test = None
with open(args.test, "r") as test_file:
    test = json.load(test_file)
if test["scenario"] not in SCENARIOS:
    raise Exception(f"unknown scenario: {test['scenario']}")
scenario = SCENARIOS[test["scenario"]]()
scenario.validate(test)

results = {
    "name": test["name"],
    "test_runs": {},
    "result": Result.PASSED,
    "run_id": args.run_id
}

for i in range(0, args.repeat):
    if test["name"] not in results["test_runs"]:
        results["test_runs"][test["name"]] = {}
    
    experiment_id = str(int(time.time()))

    mkdir("-p", f"/mnt/vectorized/experiments/{experiment_id}")
    handler = FileHandler(f"/mnt/vectorized/experiments/{experiment_id}/log")
    handler.setFormatter(formatter)
    chaos_logger.addHandler(handler)
    tasks_logger.addHandler(handler)
    
    try:
        fault = test["fault"]
        scenario = SCENARIOS[test["scenario"]]()
        description = scenario.execute(test, experiment_id)
        results["test_runs"][test["name"]][experiment_id] = description["result"]
    except:
        e, v = sys.exc_info()[:2]
        trace = traceback.format_exc()
        chaos_logger.error(v)
        chaos_logger.error(trace)
        results["test_runs"][test["name"]][experiment_id] = "UNKNOWN"
    finally:
        handler.flush()
        handler.close()
        chaos_logger.removeHandler(handler)
        tasks_logger.removeHandler(handler)
    results["result"] = Result.more_severe(results["result"], results["test_runs"][test["name"]][experiment_id])

    with open(f"/mnt/vectorized/experiments/{args.run_id}.json", "w") as info:
        info.write(json.dumps(results, indent=2))
    with open(f"/mnt/vectorized/experiments/latest.json", "w") as info:
        info.write(json.dumps(results, indent=2))