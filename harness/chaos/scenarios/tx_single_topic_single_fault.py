from chaos.scenarios.abstract_single_fault import AbstractSingleFault, ProgressException
from chaos.types import TimeoutException
from sh import mkdir
from chaos.faults.all import FAULTS
from chaos.workloads.all import WORKLOADS, wait_all_workloads_killed
from time import sleep
from chaos.checks.result import Result
import copy

import logging

from chaos.redpanda_static_cluster import RedpandaCluster

logger = logging.getLogger("chaos")

class TxSingleTopicSingleFault(AbstractSingleFault):
    SUPPORTED_WORKLOADS = {
        "tx-single-reads-writes / java", "tx-writes / java", "tx-compact / java"
    }

    SUPPORTED_FAULTS = {
        "isolate_controller", "isolate_follower", "isolate_leader",
        "kill_follower", "kill_leader", "leadership_transfer", "baseline",
        "reconfigure_11_kill", "reconfigure_313", "reconfigure_kill_11",
        "pause_follower", "pause_leader", "kill_all", "isolate_clients_kill_leader",
        "isolate_all", "rolling_restart", "kill_tx_leader", "kill_tx_follower",
        "isolate_tx_leader", "isolate_tx_follower", "recycle_all",
        "hijack_tx_ids", "isolate_tx_all", "pause_all", "kill_partition", "repeat",
        "as_oneoff", "trigger_kip_360"
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

        for host in self.redpanda_cluster.hosts:
            node_id = self.redpanda_cluster.get_id()
            if host == self.redpanda_cluster.hosts[0]:
                self.redpanda_cluster.add_seed(host, node_id)
            else:
                self.redpanda_cluster.add_node(host, node_id)

        log_levels = self.read_config(["settings", "log-level"], { "default": "info" })
        self.redpanda_cluster.launch_everywhere(self.read_config(["settings", "redpanda"], {}), log_levels)
        self.redpanda_cluster.wait_alive(timeout_s=10)
        self.redpanda_cluster.get_stable_view(timeout_s=60)

        sleep(5)
        # waiting for the controller to be up before creating a topic
        self.redpanda_cluster.wait_leader("controller", namespace="redpanda", replication=len(self.redpanda_cluster.nodes), timeout_s=30)

        cleanup = self.read_config(["settings", "cleanup"], "delete")

        logger.info(f"creating \"{self.topic}\" topic with replication factor {self.replication}")
        self.redpanda_cluster.create_topic(self.topic, self.replication, 1, cleanup)
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
        
        ### distributing internal and data topic across different nodes
        wait_progress_timeout_s = self.read_config(["settings", "setup", "wait_progress_timeout_s"], 20)
        
        logger.info(f"waiting for progress")
        try:
            self.workload_cluster.wait_progress(timeout_s=wait_progress_timeout_s)
        except TimeoutException:
            raise ProgressException()
        logger.info(f"waiting for id_allocator")
        self.redpanda_cluster.wait_leader("id_allocator", namespace="kafka_internal", replication=3, timeout_s=10)
        logger.info(f"waiting for tx coordinator")
        self.redpanda_cluster.wait_leader("tx", namespace="kafka_internal", replication=3, timeout_s=10)

        logger.info(f"warming up for 20s")
        sleep(20)

        # pick topic's nodes
        topic_info = self.redpanda_cluster.wait_details(self.topic, replication=self.replication, timeout_s=10)
        is_topic_node_id = {node.id: True for node in topic_info.replicas}
        # pick other nodes
        others = [node for node in self.redpanda_cluster.nodes if node.id not in is_topic_node_id]
        if len(others) != 3:
            raise Exception(f"len(others)={len(others)} isn't 3")
        # reconfigure id_allocator to use other nodes
        self._reconfigure(others, "id_allocator", partition=0, namespace="kafka_internal", timeout_s=20)
        # reconfigure tx to use other nodes
        self._reconfigure(others, "tx", partition=0, namespace="kafka_internal", timeout_s=20)

        try:
            self.workload_cluster.wait_progress(timeout_s=wait_progress_timeout_s)
        except TimeoutException:
            raise ProgressException()

        # transfer controller to other[0]
        self._transfer(others[0], "controller", partition=0, namespace="redpanda", timeout_s=10)

        # transfer id_allocator to other[1]
        self._transfer(others[1], "id_allocator", partition=0, namespace="kafka_internal", timeout_s=10)
        
        # transfer tx to other[2]
        self._transfer(others[2], "tx", partition=0, namespace="kafka_internal", timeout_s=10)

        try:
            self.workload_cluster.wait_progress(timeout_s=wait_progress_timeout_s)
        except TimeoutException:
            raise ProgressException()
        warmup_s = self.read_config(["settings", "setup", "warmup_s"], 20)
        if warmup_s > 0:
            logger.info(f"warming up for {warmup_s}s")
            sleep(warmup_s)