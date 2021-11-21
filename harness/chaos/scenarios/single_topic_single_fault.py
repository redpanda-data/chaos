import os
from sh import ssh, scp, python3, cd, mkdir, rm
import json
import sh
import time
import requests
from chaos.checks.all import CHECKS
from chaos.faults.all import FAULTS
from chaos.faults.types import FaultType
from chaos.workloads.all import WORKLOADS, wait_all_workloads_killed
from time import sleep
from chaos.checks.result import Result
import copy

import logging

from chaos.redpanda_cluster import RedpandaCluster

logger = logging.getLogger("chaos")

SUPPORTED_WORKLOADS = {
    "writing / kafka-clients", "writing / confluent-kafka", "writing / list-offsets", "writing / reads-writes"
}

SUPPORTED_FAULTS = [
    "isolate_controller", "isolate_follower", "isolate_leader",
    "kill_follower", "kill_leader", "leadership_transfer", "baseline",
    "reconfigure_11_kill", "reconfigure_313", "reconfigure_kill_11",
    "pause_follower", "pause_leader", "kill_all"
]

SUPPORTED_CHECKS = [
    "redpanda_process_liveness", "progress_during_fault"
]

def normalize_fault(cfg_fault):
    if cfg_fault == None:
        return None
    if isinstance(cfg_fault, str):
        return {
            "name": cfg_fault
        }
    elif isinstance(cfg_fault, dict):
        return cfg_fault
    else:
        raise Exception(f"unknown fault type: {type(cfg_fault)}")

class SingleTopicSingleFault:
    def __init__(self):
        self.redpanda_cluster = None
        self.workload_cluster = None
        self.config = None
        self.topic = None
        self.partition = None
        self.replication = None
        self.is_workload_log_fetched = False
        self.is_redpanda_log_fetched = False
    
    def validate(self, config):
        if config["workload"]["name"] not in SUPPORTED_WORKLOADS:
            raise Exception(f"unknown workload: {config['workload']}")
        if config["fault"] != None:
            fault = normalize_fault(config["fault"])
            if fault["name"] not in SUPPORTED_FAULTS:
                raise Exception(f"unknown fault: {fault['name']}")
        for check in config["checks"]:
            if check["name"] not in SUPPORTED_CHECKS:
                raise Exception(f"unknown check: {check['name']}")
            if check["name"] == "progress_during_fault":
                fault = normalize_fault(config["fault"])
                if fault == None:
                    raise Exception(f"progress_during_fault works only with faults, found None")
                fault = FAULTS[fault["name"]](fault)
                if fault.fault_type != FaultType.RECOVERABLE:
                    raise Exception(f"progress_during_fault works only with {FaultType.RECOVERABLE} faults, found {fault.fault_type}")
    
    def save_config(self):
        with open(f"/mnt/vectorized/experiments/{self.config['experiment_id']}/info.json", "w") as info:
            info.write(json.dumps(self.config, indent=2))
    
    def fetch_workload_logs(self):
        if self.workload_cluster != None:
            if self.is_workload_log_fetched:
                return
            logger.info(f"stopping workload everywhere")
            try:
                self.workload_cluster.stop_everywhere()
            except:
                pass
            self.workload_cluster.kill_everywhere()
            self.workload_cluster.wait_killed(timeout_s=10)
            for node in self.workload_cluster.nodes:
                logger.info(f"fetching oplog from {node.ip}")
                mkdir("-p", f"/mnt/vectorized/experiments/{self.config['experiment_id']}/{node.ip}")
                scp(f"ubuntu@{node.ip}:/mnt/vectorized/workloads/logs/{self.config['experiment_id']}/{node.ip}/workload.log",
                    f"/mnt/vectorized/experiments/{self.config['experiment_id']}/{node.ip}/workload.log")
            self.is_workload_log_fetched = True
    
    def fetch_redpanda_logs(self):
        if self.redpanda_cluster != None:
            if self.is_redpanda_log_fetched:
                return
            logger.info(f"stopping redpanda")
            self.redpanda_cluster.kill_everywhere()
            self.redpanda_cluster.wait_killed(timeout_s=10)
            mkdir("-p", f"/mnt/vectorized/experiments/{self.config['experiment_id']}/redpanda")
            for node in self.redpanda_cluster.nodes:
                mkdir("-p", f"/mnt/vectorized/experiments/{self.config['experiment_id']}/redpanda/{node.ip}")
                logger.info(f"fetching logs from {node.ip}")
                scp(
                    f"ubuntu@{node.ip}:/mnt/vectorized/redpanda/log.*",
                    f"/mnt/vectorized/experiments/{self.config['experiment_id']}/redpanda/{node.ip}/")
            self.is_redpanda_log_fetched = True
    
    def remove_logs(self):
        for node in self.workload_cluster.nodes:
            rm("-rf", f"/mnt/vectorized/experiments/{self.config['experiment_id']}/{node.ip}/workload.log")
        rm("-rf", f"/mnt/vectorized/experiments/{self.config['experiment_id']}/redpanda")
    
    def get_progress_during_fault(self):
        for check_cfg in self.config["checks"]:
            if check_cfg["name"] == "progress_during_fault":
                return check_cfg
        return None
    
    def _execute(self):
        logger.info(f"stopping workload everywhere (if running)")
        wait_all_workloads_killed("/mnt/vectorized/client.nodes")

        self.workload_cluster = WORKLOADS[self.config["workload"]["name"]]("/mnt/vectorized/client.nodes")
        self.config["workload"]["nodes"] = []
        for node in self.workload_cluster.nodes:
            self.config["workload"]["nodes"].append(node.ip)

        self.redpanda_cluster = RedpandaCluster("/mnt/vectorized/redpanda.nodes")

        fault = normalize_fault(self.config["fault"])
        if fault != None:
            fault = FAULTS[fault["name"]](fault)
        
        self.config["brokers"] = self.redpanda_cluster.brokers()

        self.save_config()
        
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
        self.workload_cluster.launch_everywhere()
        self.workload_cluster.wait_alive(timeout_s=10)
        self.workload_cluster.wait_ready(timeout_s=10)

        for node in self.workload_cluster.nodes:
            logger.info(f"init workload with brokers=\"{self.redpanda_cluster.brokers()}\" and topic=\"{self.topic}\" on {node.ip}")
            self.workload_cluster.init(node, node.ip, self.redpanda_cluster.brokers(), self.topic, self.config['experiment_id'], self.config["workload"]["settings"])

        for node in self.workload_cluster.nodes:
            logger.info(f"starting workload on {node.ip}")
            self.workload_cluster.start(node)
        
        logger.info(f"warming up")
        while True:
            logger.info(f"waiting for progress")
            self.workload_cluster.wait_progress(timeout_s=10)

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
        for node in self.workload_cluster.nodes:
            self.workload_cluster.emit_event(node, "measure")

        if fault == None:
            logger.info(f"wait for 180 seconds to record steady state")
            sleep(180)
        elif fault.fault_type==FaultType.RECOVERABLE:
            logger.info(f"wait for 60 seconds to record steady state")
            sleep(60)
            for node in self.workload_cluster.nodes:
                self.workload_cluster.emit_event(node, "injecting")
            logger.info(f"injecting {fault.name}")
            fault.inject(self)
            logger.info(f"injected {fault.name}")
            for node in self.workload_cluster.nodes:
                self.workload_cluster.emit_event(node, "injected")
            after_fault_info = {}
            for node in self.workload_cluster.nodes:
                after_fault_info[node.ip] = self.workload_cluster.info(node)
            logger.info(f"wait for 60 seconds to record impacted state")
            sleep(60)
            before_heal_info = {}
            for node in self.workload_cluster.nodes:
                before_heal_info[node.ip] = self.workload_cluster.info(node)
            progress_during_fault = self.get_progress_during_fault()
            if progress_during_fault != None:
                progress_during_fault["result"] = Result.PASSED
                for ip in before_heal_info.keys():
                    delta = before_heal_info[ip].succeeded_ops - after_fault_info[ip].succeeded_ops
                    progress_during_fault[ip] = {
                        "delta": delta
                    }
                    if delta < progress_during_fault["min-delta"]:
                        progress_during_fault[ip]["result"] = Result.FAILED
                    else:
                        progress_during_fault[ip]["result"] = Result.PASSED
                    progress_during_fault["result"] = Result.more_severe(
                        progress_during_fault["result"],
                        progress_during_fault[ip]["result"]
                    )
                self.config["result"] = Result.more_severe(
                    self.config["result"],
                    progress_during_fault["result"]
                )
                self.save_config()
            for node in self.workload_cluster.nodes:
                self.workload_cluster.emit_event(node, "healing")
            logger.info(f"healing {fault.name}")
            fault.heal(self)
            logger.info(f"healed {fault.name}")
            for node in self.workload_cluster.nodes:
                self.workload_cluster.emit_event(node, "healed")
            logger.info(f"wait for 60 seconds to record recovering state")
            sleep(60)
        elif fault.fault_type==FaultType.ONEOFF:
            logger.info(f"wait for 60 seconds to record steady state")
            sleep(60)
            for node in self.workload_cluster.nodes:
                self.workload_cluster.emit_event(node, "injecting")
            logger.info(f"injecting {fault.name}")
            fault.execute(self)
            logger.info(f"injected {fault.name}")
            for node in self.workload_cluster.nodes:
                self.workload_cluster.emit_event(node, "injected")
            logger.info(f"wait for 120 seconds to record impacted / recovering state")
            sleep(120)
        else:
            raise Exception(f"Unknown fault type {fault.fault_type}")

        self.fetch_workload_logs()

        for check_cfg in self.config["checks"]:
            if check_cfg["name"] == "progress_during_fault":
                continue
            check = CHECKS[check_cfg["name"]]
            result = check().check(self)
            for key in result:
                check_cfg[key] = result[key]
            self.config["result"] = Result.more_severe(self.config["result"], check_cfg["result"])
        self.save_config()

        self.config = self.workload_cluster.analyze(copy.deepcopy(self.config))
        logger.info(f"experiment {self.config['experiment_id']} result: {self.config['result']}")
        self.save_config()
        
        self.fetch_redpanda_logs()

        if "settings" in self.config:
            if "remove_logs_on_success" in self.config["settings"]:
                if self.config["settings"]["remove_logs_on_success"]:
                    if self.config["result"]==Result.PASSED:
                        self.remove_logs()
        
        return self.config
    
    def execute(self, config, experiment_id):
        self.config = copy.deepcopy(config)
        self.topic = self.config["topic"]
        self.replication = self.config["replication"]
        self.partition = 0
        self.config["experiment_id"] = experiment_id
        self.config["result"] = Result.PASSED
        logger.info(f"starting experiment {self.config['name']} (id={self.config['experiment_id']})")
        
        mkdir("-p", f"/mnt/vectorized/experiments/{self.config['experiment_id']}")
        
        try:
            return self._execute()
        except:
            self.config["result"] = Result.more_severe(self.config["result"], Result.UNKNOWN)
            self.save_config()
            raise
        finally:
            try:
                self.fetch_workload_logs()
            except:
                pass
            try:
                self.fetch_redpanda_logs()
            except:
                pass