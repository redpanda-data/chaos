import sys
import os.path
import json
from chaos.workloads.reads_writes import consistency
from chaos.workloads.reads_writes import stat

check_type = sys.argv[1]
config_filename = sys.argv[2]
workload_dir = sys.argv[3]

config = None
with open(config_filename, "r") as config_file:
    config = json.load(config_file)

if check_type == "consistency":
    result = consistency.validate(config, workload_dir)
    with open(os.path.join(workload_dir, "consistency.json"), "w") as consistency_file:
        consistency_file.write(json.dumps(result))
elif check_type == "stat":
    stat.collect(config, workload_dir)
else:
    raise Exception(f"unknown check type: {check_type}")