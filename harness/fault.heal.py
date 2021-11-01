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
    "kill_leader": KillLeaderFault()
}

def heal_fault(fault, workload_cluster):
    redpanda_cluster = RedpandaCluster("/mnt/vectorized/redpanda.nodes")
    if fault.fault_type=="RECOVERABLE":
        fault.attach("topic1", 3, 0)
        for node in workload_cluster.nodes:
            workload_cluster.emit_event(node, "healing")
        fault.heal(redpanda_cluster)
        for node in workload_cluster.nodes:
            workload_cluster.emit_event(node, "healed")
    else:
        raise Exception(f"unknown fault type: {fault.fault_type}")

run_id = sys.argv[1]

data = None

with open(f"/mnt/vectorized/faults/{run_id}", "r") as info_file:
    data = json.load(info_file)

if data["fault"] not in faults:
    raise Exception(f"Unsupported fault: {fault}")
fault = faults[data["fault"]]
fault.load(data)

workload_cluster = WorkloadCluster("/mnt/vectorized/client.nodes")
heal_fault(fault, workload_cluster)