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
    experiment = str(int(time.time()))
    mkdir(f"/mnt/vectorized/experiments/{experiment}")

    with open(f"/mnt/vectorized/experiments/interactive", "w") as interactive:
        interactive.write(json.dumps({
            "experiment": experiment
        }))

    with open(f"/mnt/vectorized/experiments/{experiment}/info", "w") as info:
        info.write(json.dumps({
            "name": f"{workload_cluster.name} / interactive",
            "fault_type": "INTERACTIVE"
        }))

    redpanda_cluster = RedpandaCluster("/mnt/vectorized/redpanda.nodes")

    print("stopping redpanda")
    for node in redpanda_cluster.nodes:
        redpanda_cluster.kill(node)

    print("cleaning redpanda")
    for node in redpanda_cluster.nodes:
        redpanda_cluster.clean(node)

    print("starting redpanda")
    for node in redpanda_cluster.nodes:
        redpanda_cluster.launch(node)
    
    is_running = False
    while not is_running:
        print("is redpanda running?")
        is_running = True
        for node in redpanda_cluster.nodes:
            is_running = is_running and redpanda_cluster.is_alive(node)
        if not is_running:
            sleep(1)
    
    redpanda_cluster.create_topic("topic1", 3, 1)

    topic_leader = None
    while topic_leader == None:
        print("getting \"topic1\" leader")
        topic_leader = redpanda_cluster.get_leader("topic1", 3, 0)
        if topic_leader == None:
            sleep(1)
    print(f"\"topic1\" leader: {topic_leader}")

    controller_leader = None
    while controller_leader == None:
        print("getting controller leader")
        controller_leader = redpanda_cluster.get_leader("controller", 3, 0, namespace="redpanda")
        if controller_leader == None:
            sleep(1)
    print(f"controller leader: {controller_leader}")

    if topic_leader == controller_leader:
        node = redpanda_cluster.any_node_but_address(topic_leader)
        redpanda_cluster.transfer_leadership_to("kafka", "topic1", 0, 3, node.id)

    for node in workload_cluster.nodes:
        workload_cluster.kill(node)

    for node in workload_cluster.nodes:
        workload_cluster.launch(node)

    is_running = False
    while not is_running:
        print("is workload process alive?")
        is_running = True
        for node in workload_cluster.nodes:
            is_running = is_running and workload_cluster.is_alive(node)
        if not is_running:
            sleep(1)

    for node in workload_cluster.nodes:
        workload_cluster.init(node, node.ip, redpanda_cluster.brokers(), "topic1", experiment)

    for node in workload_cluster.nodes:
        workload_cluster.start(node)

    started = dict()
    for node in workload_cluster.nodes:
        started[node.ip]=workload_cluster.info(node)
    made_progress = False
    while not made_progress:
        print("progress?")
        made_progress = True
        for node in workload_cluster.nodes:
            info = workload_cluster.info(node)
            made_progress = made_progress and info.succeeded_ops > started[node.ip].succeeded_ops
        if not made_progress:
            sleep(1)

workload_cluster = WorkloadCluster("/mnt/vectorized/client.nodes")
execute_scenario(workload_cluster)
