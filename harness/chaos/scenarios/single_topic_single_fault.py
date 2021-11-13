import os
from sh import ssh
from sh import scp
from sh import python3
from sh import cd
from sh import mkdir
import json
import sh
import time
import requests
from chaos.checks.all import CHECKS
from chaos.faults.all import FAULTS
from chaos.workloads.all import WORKLOADS, wait_all_workloads_killed
from time import sleep
from chaos.checks.result import Result
import copy

import logging

from chaos.redpanda_cluster import RedpandaCluster

logger = logging.getLogger("chaos")

SUPPORTED_WORKLOADS = {
    "writing / kafka-clients", "writing / confluent-kafka", "writing / list-offsets"
}

SUPPORTED_FAULTS = [
    "isolate_controller", "isolate_follower", "isolate_leader", "kill_follower", "kill_leader", "leadership_transfer", "baseline"
]

SUPPORTED_CHECKS = [
    "redpanda_process_liveness"
]

class SingleTopicSingleFault:
    def __init__(self):
        self.redpanda_cluster = None
        self.config = None
        self.topic = None
        self.partition = None
        self.replication = None
    
    def validate(self, config):
        if config["workload"]["name"] not in SUPPORTED_WORKLOADS:
            raise Exception(f"unknown workload: {config['workload']}")
        if config["fault"] != None and config["fault"] not in SUPPORTED_FAULTS:
            raise Exception(f"unknown fault: {config['fault']}")
        for check in config["checks"]:
            if check["name"] not in SUPPORTED_CHECKS:
                raise Exception(f"unknown check: {check['name']}")
    
    def execute(self, config, experiment_id):
        self.config = copy.deepcopy(config)
        self.topic = self.config["topic"]
        self.replication = self.config["replication"]
        self.partition = 0
        self.config["experiment_id"] = experiment_id
        self.config["result"] = Result.PASSED
        logger.info(f"starting experiment {self.config['name']} (id={experiment_id})")
        
        mkdir("-p", f"/mnt/vectorized/experiments/{experiment_id}")
        
        logger.info(f"stopping workload everywhere (if running)")
        wait_all_workloads_killed("/mnt/vectorized/client.nodes")

        workload_cluster = WORKLOADS[self.config["workload"]["name"]]("/mnt/vectorized/client.nodes")

        self.redpanda_cluster = RedpandaCluster("/mnt/vectorized/redpanda.nodes")

        fault = self.config["fault"]
        if fault != None:
            fault = FAULTS[fault]()
        
        self.config["brokers"] = self.redpanda_cluster.brokers()

        with open(f"/mnt/vectorized/experiments/{experiment_id}/info.json", "w") as info:
            info.write(json.dumps(self.config, indent=2))
        
        logger.info(f"undoing faults")
        self.redpanda_cluster.heal()

        logger.info(f"(re-)starting fresh redpanda cluster")
        self.redpanda_cluster.kill_everywhere()
        self.redpanda_cluster.wait_killed(timeout_s=10)
        self.redpanda_cluster.clean_everywhere()
        self.redpanda_cluster.launch_everywhere()
        self.redpanda_cluster.wait_alive(timeout_s=10)

        # waiting for the controller to be up before creating a topic
        self.redpanda_cluster.wait_leader("controller", namespace="redpanda", replication=3, timeout_s=20)

        logger.info(f"creating \"{self.topic}\" topic with replication factor {self.replication}")
        self.redpanda_cluster.create_topic(self.topic, self.replication, 1)
        # waiting for the topic to come online
        self.redpanda_cluster.wait_leader(self.topic, replication=self.replication, timeout_s=20)

        logger.info(f"launching workload service")
        workload_cluster.launch_everywhere()
        workload_cluster.wait_alive(timeout_s=10)
        workload_cluster.wait_ready(timeout_s=10)

        for node in workload_cluster.nodes:
            logger.info(f"init workload with brokers=\"{self.redpanda_cluster.brokers()}\" and topic=\"{self.topic}\" on {node.ip}")
            workload_cluster.init(node, node.ip, self.redpanda_cluster.brokers(), self.topic, experiment_id, self.config["workload"]["settings"])

        for node in workload_cluster.nodes:
            logger.info(f"starting workload on {node.ip}")
            workload_cluster.start(node)
        
        logger.info(f"warming up")
        while True:
            logger.info(f"waiting for progress")
            workload_cluster.wait_progress(timeout_s=10)

            logger.info(f"warming up for 20s")
            sleep(20)
            
            topic_leader = self.redpanda_cluster.wait_leader(self.topic, timeout_s=10)
            logger.debug(f"leader of \"{self.topic}\": {topic_leader.ip} (id={topic_leader.id})")
            
            controller_leader = self.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=10)
            logger.debug(f"controller leader: {controller_leader.ip} (id={controller_leader.id})")

            if topic_leader == controller_leader:
                target = self.redpanda_cluster.any_node_but(topic_leader)
                self.redpanda_cluster.transfer_leadership_to(target, "redpanda", "controller", 0)
                self.redpanda_cluster.wait_leader_is(target, "redpanda", "controller", 0, timeout_s=10)
                continue
            
            break
        
        logger.info(f"start measuring")
        for node in workload_cluster.nodes:
            workload_cluster.emit_event(node, "measure")

        if fault == None:
            logger.info(f"wait for 180 seconds to record steady state")
            sleep(180)
        elif fault.fault_type=="RECOVERABLE":
            logger.info(f"wait for 60 seconds to record steady state")
            sleep(60)
            for node in workload_cluster.nodes:
                workload_cluster.emit_event(node, "injecting")
            logger.info(f"injecting {fault.name}")
            fault.inject(self)
            logger.info(f"injected {fault.name}")
            for node in workload_cluster.nodes:
                workload_cluster.emit_event(node, "injected")
            logger.info(f"wait for 60 seconds to record impacted state")
            sleep(60)
            for node in workload_cluster.nodes:
                workload_cluster.emit_event(node, "healing")
            logger.info(f"healing {fault.name}")
            fault.heal(self)
            logger.info(f"healed {fault.name}")
            for node in workload_cluster.nodes:
                workload_cluster.emit_event(node, "healed")
            logger.info(f"wait for 60 seconds to record recovering state")
            sleep(60)
        elif fault.fault_type=="ONEOFF":
            logger.info(f"wait for 60 seconds to record steady state")
            sleep(60)
            for node in workload_cluster.nodes:
                workload_cluster.emit_event(node, "injecting")
            logger.info(f"injecting {fault.name}")
            fault.execute(self)
            logger.info(f"healed {fault.name}")
            for node in workload_cluster.nodes:
                workload_cluster.emit_event(node, "healed")
            logger.info(f"wait for 120 seconds to record impacted / recovering state")
            sleep(120)

        logger.info(f"stopping workload everywhere")
        workload_cluster.stop_everywhere()
        workload_cluster.kill_everywhere()
        workload_cluster.wait_killed(timeout_s=10)

        for check_cfg in self.config["checks"]:
            check = CHECKS[check_cfg["name"]]
            result = check().check(self)
            for key in result:
                check_cfg[key] = result[key]
            self.config["result"] = Result.more_severe(self.config["result"], check_cfg["result"])
        
        self.config["workload"]["nodes"] = []
        for node in workload_cluster.nodes:
            logger.info(f"fetching oplog from {node.ip}")
            self.config["workload"]["nodes"].append(node.ip)
            scp("-r", f"ubuntu@{node.ip}:/mnt/vectorized/workloads/logs/{experiment_id}/*", f"/mnt/vectorized/experiments/{experiment_id}/")
        
        with open(f"/mnt/vectorized/experiments/{experiment_id}/info.json", "w") as info:
            info.write(json.dumps(self.config, indent=2))

        self.config = workload_cluster.analyze(copy.deepcopy(self.config))
        logger.info(f"experiment {experiment_id} result: {self.config['result']}")
        with open(f"/mnt/vectorized/experiments/{experiment_id}/info.json", "w") as info:
            info.write(json.dumps(self.config, indent=2))
        
        logger.info(f"stopping redpanda")
        self.redpanda_cluster.kill_everywhere()
        self.redpanda_cluster.wait_killed(timeout_s=10)

        mkdir(f"/mnt/vectorized/experiments/{experiment_id}/redpanda")
        for node in self.redpanda_cluster.nodes:
            mkdir(f"/mnt/vectorized/experiments/{experiment_id}/redpanda/{node.ip}")
            logger.info(f"fetching logs from {node.ip}")
            scp(
                f"ubuntu@{node.ip}:/mnt/vectorized/redpanda/log",
                f"/mnt/vectorized/experiments/{experiment_id}/redpanda/{node.ip}/log")
        
        return self.config