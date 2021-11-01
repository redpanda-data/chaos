from sh import ssh
from sh import scp
from sh import python3
from sh import cd
from sh import mkdir
import json
import sh
import time
import requests
import sys
from time import sleep

from chaos.faults.isolate_controller import IsolateControllerFault
from chaos.faults.isolate_follower import IsolateFollowerFault
from chaos.faults.isolate_leader import IsolateLeaderFault
from chaos.faults.kill_follower import KillFollowerFault
from chaos.faults.kill_leader import KillLeaderFault
from chaos.faults.leadership_transfer import LeadershipTransferFault

from chaos.workload_cluster import WorkloadCluster
from chaos.redpanda_cluster import RedpandaCluster

faults = {
    "isolate_controller": IsolateControllerFault(),
    "isolate_follower": IsolateFollowerFault(),
    "isolate_leader": IsolateLeaderFault(),
    "kill_follower": KillFollowerFault(),
    "kill_leader": KillLeaderFault(),
    "leadership_transfer": LeadershipTransferFault()
}

def inject_fault(fault, workload_cluster):
    redpanda_cluster = RedpandaCluster("/mnt/vectorized/redpanda.nodes")
    if fault.fault_type=="RECOVERABLE":
        fault.attach("topic1", 3, 0)
        for node in workload_cluster.nodes:
            workload_cluster.emit_event(node, "injecting")
        fault.inject(redpanda_cluster)
        for node in workload_cluster.nodes:
            workload_cluster.emit_event(node, "injected")
    elif fault.fault_type=="ONEOFF":
        fault.attach("topic1", 3, 0)
        for node in workload_cluster.nodes:
            workload_cluster.emit_event(node, "injecting")
        fault.execute(redpanda_cluster)
        for node in workload_cluster.nodes:
            workload_cluster.emit_event(node, "healed")
    else:
        raise Exception(f"unknown fault type: {fault.fault_type}")

fault = sys.argv[1]
run_id = sys.argv[2]

if fault not in faults:
    raise Exception(f"Unsupported fault: {fault}")

fault = faults[fault]

workload_cluster = WorkloadCluster("/mnt/vectorized/client.nodes")
inject_fault(fault, workload_cluster)
data = fault.export()
data["fault"] = sys.argv[1]
with open(f"/mnt/vectorized/faults/{run_id}", "w") as interactive:
    interactive.write(json.dumps(data))