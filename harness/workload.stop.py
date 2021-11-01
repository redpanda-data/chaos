from sh import ssh
from sh import scp
from sh import python3
from sh import cd
from sh import mkdir
import json
import sh
import time
import requests
from time import sleep

from chaos.workload_cluster import WorkloadCluster
from chaos.redpanda_cluster import RedpandaCluster

def execute_scenario(workload_cluster):
    experiment = None
    with open(f"/mnt/vectorized/experiments/interactive", "r") as interactive_file:
        info = json.load(interactive_file)
        experiment=info["experiment"]
    
    for node in workload_cluster.nodes:
        workload_cluster.stop(node)
    
    redpanda_cluster = RedpandaCluster("/mnt/vectorized/redpanda.nodes")
    mkdir(f"/mnt/vectorized/experiments/{experiment}/redpanda")
    for node in redpanda_cluster.nodes:
        redpanda_cluster.kill(node)
        mkdir(f"/mnt/vectorized/experiments/{experiment}/redpanda/{node.ip}")
        scp(f"ubuntu@{node.ip}:/mnt/vectorized/redpanda/log", f"/mnt/vectorized/experiments/{experiment}/redpanda/{node.ip}/log")

    for node in workload_cluster.nodes:
        scp("-r", f"ubuntu@{node.ip}:/mnt/vectorized/workloads/logs/{experiment}/*", f"/mnt/vectorized/experiments/{experiment}/")
        cd(f"/mnt/vectorized/experiments/{experiment}/{node.ip}")
        python3("/mnt/vectorized/workloads/writing/analysis/report.py", f"/mnt/vectorized/experiments/{experiment}/info", f"/mnt/vectorized/experiments/{experiment}/{node.ip}/workload.log")

workload_cluster = WorkloadCluster("/mnt/vectorized/client.nodes")
execute_scenario(workload_cluster)
