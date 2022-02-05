from chaos.scenarios.abstract_single_fault import AbstractSingleFault
from sh import mkdir
from chaos.faults.all import FAULTS
from chaos.workloads.all import WORKLOADS, wait_all_workloads_killed
from time import sleep
from chaos.checks.result import Result
import copy

import logging

from chaos.redpanda_static_cluster import RedpandaCluster

logger = logging.getLogger("chaos")

class TxPollSingleFault(AbstractSingleFault):
    SUPPORTED_WORKLOADS = {
        "tx-poll / java"
    }

    SUPPORTED_FAULTS = {
        "isolate_controller", "isolate_leader", "kill_leader", "leadership_transfer",
        "baseline", "pause_follower", "pause_leader", "kill_all", "isolate_clients_kill_leader",
        "isolate_all", "rolling_restart", "kill_tx_leader", "kill_tx_follower",
        "isolate_tx_leader", "isolate_tx_follower", "pause_all",
        "hijack_tx_ids", "isolate_tx_all", "reconfigure_313", "kill_follower",
        "isolate_client_topic_leader", "stop_client", "repeat", "as_oneoff"
    }

    SUPPORTED_CHECKS = {
        "redpanda_process_liveness", "progress_during_fault"
    }

    def __init__(self):
        super().__init__()
        self.topics = None
        self.partitions = None
        self.replication = None
    
    def prepare_experiment(self, config, experiment_id):
        self.config = copy.deepcopy(config)
        self.topics = self.config["workload"]["settings"]["topics"]
        self.replication = self.config["replication"]
        if self.replication != 3:
            raise Exception("only replication factor of 3 is supported wit tx-money scenario")
        self.partitions = self.config["workload"]["settings"]["partitions"]
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
        self.redpanda_cluster.launch_everywhere(self.read_config(["settings", "redpanda"], {}))
        self.redpanda_cluster.wait_alive(timeout_s=10)

        sleep(5)
        # waiting for the controller to be up before creating a topic
        self.redpanda_cluster.wait_leader("controller", namespace="redpanda", replication=len(self.redpanda_cluster.nodes), timeout_s=30)

        logger.info(f"creating {self.topics} topics with replication factor {self.replication} & {self.partitions} partitions")
        for topic in range(0, self.topics):
            self.redpanda_cluster.create_topic(f"topic{topic}", self.replication, self.partitions)

        # waiting for the topic to come online
        for topic in range(0, self.topics):
            for partition in range(0, self.partitions):
                self.redpanda_cluster.wait_leader(f"topic{topic}", partition=partition, replication=self.replication, timeout_s=20)

        logger.info(f"launching workload service")
        self.workload_cluster.launch_everywhere()
        self.workload_cluster.wait_alive(timeout_s=10)
        sleep(5)
        self.workload_cluster.wait_ready(timeout_s=10)

        for node in self.workload_cluster.nodes:
            logger.info(f"init workload with brokers=\"{self.redpanda_cluster.brokers()}\" on {node.ip}")
            self.workload_cluster.init(node, node.ip, self.redpanda_cluster.brokers(), self.config['experiment_id'], self.config["workload"]["settings"])

        for node in self.workload_cluster.nodes:
            logger.info(f"starting workload on {node.ip}")
            self.workload_cluster.start(node)
        
        ### distributing internal and data topic across different nodes
        wait_progress_timeout_s = self.read_config(["settings", "setup", "wait_progress_timeout_s"], 20)
        
        logger.info(f"waiting for progress")
        self.workload_cluster.wait_progress(timeout_s=wait_progress_timeout_s)
        logger.info(f"waiting for id_allocator")
        self.redpanda_cluster.wait_leader("id_allocator", namespace="kafka_internal", replication=3, timeout_s=10)
        logger.info(f"waiting for tx coordinator")
        self.redpanda_cluster.wait_leader("tx", namespace="kafka_internal", replication=3, timeout_s=10)
        logger.info(f"waiting for consumer groups")
        self.redpanda_cluster.wait_leader("group", namespace="kafka_internal", replication=3, timeout_s=10)

        logger.info(f"warming up for 20s")
        sleep(20)

        internal_nodes = self.redpanda_cluster.nodes[0:3]
        data_nodes = self.redpanda_cluster.nodes[3:]

        # reconfigure id_allocator to use internal_nodes
        self._reconfigure(internal_nodes, "id_allocator", partition=0, namespace="kafka_internal", timeout_s=20)
        # reconfigure tx to use internal_nodes
        self._reconfigure(internal_nodes, "tx", partition=0, namespace="kafka_internal", timeout_s=20)
        # reconfigure consumer groups to use internal_nodes
        self._reconfigure(internal_nodes, "group", partition=0, namespace="kafka_internal", timeout_s=20)

        for topic in range(0, self.topics):
            for partition in range(0, self.partitions):
                self._reconfigure(data_nodes, f"topic{topic}", partition=partition, namespace="kafka", timeout_s=20)
        
        self.workload_cluster.wait_progress(timeout_s=wait_progress_timeout_s)

        # transfer controller to other[0]
        self._transfer(internal_nodes[0], "controller", partition=0, namespace="redpanda", timeout_s=20)
        # transfer id_allocator to other[1]
        self._transfer(internal_nodes[1], "id_allocator", partition=0, namespace="kafka_internal", timeout_s=20)
        # transfer consumer groups to other[1]
        self._transfer(internal_nodes[1], "group", partition=0, namespace="kafka_internal", timeout_s=20)
        # transfer tx to other[2]
        self._transfer(internal_nodes[2], "tx", partition=0, namespace="kafka_internal", timeout_s=20)

        for topic in range(0, self.topics):
            for partition in range(0, self.partitions):
                self._transfer(data_nodes[(partition + topic)%len(data_nodes)], f"topic{topic}", partition=partition, namespace="kafka", timeout_s=20)

        self.workload_cluster.wait_progress(timeout_s=wait_progress_timeout_s)
        warmup_s = self.read_config(["settings", "setup", "warmup_s"], 20)
        if warmup_s > 0:
            logger.info(f"warming up for {warmup_s}s")
            sleep(warmup_s)