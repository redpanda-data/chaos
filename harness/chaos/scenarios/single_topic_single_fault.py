from chaos.scenarios.abstract_single_fault import AbstractSingleFault
from sh import mkdir
from chaos.faults.all import FAULTS
from chaos.workloads.all import WORKLOADS, wait_all_workloads_killed
from time import sleep
from chaos.checks.result import Result
import copy
from chaos.types import TimeoutException
import sys
import traceback
import time

import logging

from chaos.redpanda_static_cluster import RedpandaCluster

logger = logging.getLogger("chaos")

class SingleTopicSingleFault(AbstractSingleFault):
    SUPPORTED_WORKLOADS = {
        "writes / java", "writes / python", "list-offsets / java", "reads-writes / java",
        "writes / concurrency"
    }

    SUPPORTED_FAULTS = {
        "isolate_controller", "isolate_follower", "isolate_leader",
        "kill_follower", "kill_leader", "leadership_transfer", "baseline",
        "reconfigure_11_kill", "reconfigure_313", "reconfigure_kill_11",
        "pause_follower", "pause_leader", "kill_all", "isolate_clients_kill_leader",
        "isolate_all", "rolling_restart", "decommission_leader", "pause_all",
        "repeat", "as_oneoff", "kill_partition", "recycle_all"
    }

    SUPPORTED_CHECKS = {
        "redpanda_process_liveness", "progress_during_fault", "catch_log_errors"
    }

    def __init__(self):
        super().__init__()
        self.topic = None
        self.partition = None
        self.replication = None
    
    def prepare_experiment(self, config, experiment_id):
        self.config = copy.deepcopy(config)
        self.topic = self.config["topic"]
        self.replication = self.config["replication"]
        self.partition = 0
        self.cleanup = self.read_config(["cleanup"], "delete")
        self.config["experiment_id"] = experiment_id
        self.config["result"] = Result.PASSED
        logger.info(f"starting experiment {self.config['name']} (id={self.config['experiment_id']})")
        
        mkdir("-p", f"/mnt/vectorized/experiments/{self.config['experiment_id']}")

        logger.info(f"stopping workload everywhere (if running)")
        wait_all_workloads_killed("/mnt/vectorized/client.nodes")

        self.workload_cluster = WORKLOADS[self.config["workload"]["name"]]("/mnt/vectorized/client.nodes")
        logger.info(f"undoing clients faults")
        self.workload_cluster.heal()
        
        self.config["workload"]["nodes"] = []
        for node in self.workload_cluster.nodes:
            self.config["workload"]["nodes"].append(node.ip)

        self.redpanda_cluster = RedpandaCluster("/mnt/vectorized/redpanda.nodes")

        self.fault = self.normalize_fault(self.config["fault"])
        if self.fault != None:
            self.fault = FAULTS[self.fault["name"]](self.fault)
        
        self.config["brokers"] = self.redpanda_cluster.brokers()
        self.save_config()
        
        logger.info(f"undoing redpanda faults")
        self.redpanda_cluster.heal()

        logger.info(f"(re-)starting fresh redpanda cluster")
        self.redpanda_cluster.kill_everywhere()
        self.redpanda_cluster.wait_killed(timeout_s=10)
        self.redpanda_cluster.clean_everywhere()
        
        for host in self.redpanda_cluster.hosts[0:3]:
            node_id = self.redpanda_cluster.get_id()
            if host == self.redpanda_cluster.hosts[0]:
                self.redpanda_cluster.add_seed(host, node_id)
            else:
                self.redpanda_cluster.add_node(host, node_id)

        self.redpanda_cluster.launch_everywhere(self.read_config(["settings", "redpanda"], {}))
        self.redpanda_cluster.wait_alive(timeout_s=10)
        self.redpanda_cluster.get_stable_view(timeout_s=60)

        sleep(5)
        # waiting for the controller to be up before creating a topic
        self.redpanda_cluster.wait_leader("controller", namespace="redpanda", replication=len(self.redpanda_cluster.nodes), timeout_s=30)

        logger.info(f"creating \"{self.topic}\" topic with replication factor {self.replication}")
        self.redpanda_cluster.create_topic(self.topic, self.replication, 1, cleanup=self.cleanup)

        # waiting for the topic to come online
        self.redpanda_cluster.wait_leader(self.topic, replication=self.replication, timeout_s=20)

        logger.info(f"launching workload service")
        self.workload_cluster.launch_everywhere()
        self.workload_cluster.wait_alive(timeout_s=10)
        sleep(5)
        self.workload_cluster.wait_ready(timeout_s=10)

        for node in self.workload_cluster.nodes:
            logger.info(f"init workload with brokers=\"{self.redpanda_cluster.brokers()}\" and topic=\"{self.topic}\" on {node.ip}")
            self.workload_cluster.init(node, node.ip, self.redpanda_cluster.brokers(), self.topic, self.config['experiment_id'], self.config["workload"]["settings"])

        for node in self.workload_cluster.nodes:
            logger.info(f"starting workload on {node.ip}")
            self.workload_cluster.start(node)
        
        wait_progress_timeout_s = self.read_config(["settings", "setup", "wait_progress_timeout_s"], 20)

        logger.info(f"waiting for progress")
        self.workload_cluster.wait_progress(timeout_s=wait_progress_timeout_s)

        topic_leader = self.redpanda_cluster.wait_leader(self.topic, timeout_s=10)
        logger.debug(f"leader of \"{self.topic}\": {topic_leader.ip} (id={topic_leader.id})")
        controller_leader = self.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=10)
        logger.debug(f"controller leader: {controller_leader.ip} (id={controller_leader.id})")

        if topic_leader == controller_leader:
            target = self.redpanda_cluster.any_node_but(topic_leader)
            self._transfer(target, topic="controller", partition=0, namespace="redpanda", timeout_s=10)
            logger.info(f"waiting for progress")
            self.workload_cluster.wait_progress(timeout_s=wait_progress_timeout_s)
        
        warmup_s = self.read_config(["settings", "setup", "warmup_s"], 20)
        if warmup_s > 0:
            logger.info(f"warming up for {warmup_s}s")
            sleep(warmup_s)