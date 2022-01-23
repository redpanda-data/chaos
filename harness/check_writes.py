import sys
import os.path
import json
from chaos.workloads.writes import consistency
from chaos.workloads.writes import stat

check_type = sys.argv[1]
experiment_dir = sys.argv[2]

config = None
with open(os.path.join(experiment_dir, "info.json"), "r") as config_file:
    config = json.load(config_file)

if check_type == "consistency":
    result = consistency.validate(config, experiment_dir)
    print(json.dumps(result))
elif check_type == "stat":
    stat_check = None
    for check in config["workload"]["checks"]:
        if check["name"] == "stat":
            stat_check = check
    result = stat.collect(config, stat_check, experiment_dir)
    print(json.dumps(result, indent=2))
else:
    raise Exception(f"unknown check type: {check_type}")