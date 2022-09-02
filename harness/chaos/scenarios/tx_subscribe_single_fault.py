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

chaos_logger = logging.getLogger("chaos")
tasks_logger = logging.getLogger("tasks")

class TxSubscribeSingleFault(AbstractSingleFault):
    SUPPORTED_WORKLOADS = {
        "tx-subscribe / java"
    }

    SUPPORTED_FAULTS = {
        "isolate_controller", "isolate_leader", "kill_leader", "leadership_transfer",
        "baseline", "pause_follower", "pause_leader", "kill_all", "isolate_clients_kill_leader",
        "isolate_all", "rolling_restart", "kill_tx_leader", "kill_tx_follower",
        "isolate_tx_leader", "isolate_tx_follower", "pause_all", "recycle_all",
        "hijack_tx_ids", "isolate_tx_all", "reconfigure_313", "kill_follower",
        "isolate_client_topic_leader", "stop_client", "kill_partition"
    }

    SUPPORTED_CHECKS = {
        "redpanda_process_liveness", "progress_during_fault"
    }

    def __init__(self):
        super().__init__()
        self.source = None
        self.target = None
        self.partitions = None
        self.replication = None
    
    def prepare_experiment(self, config, experiment_id):
        self.config = copy.deepcopy(config)
        self.source = self.config["source"]
        self.target = self.config["target"]
        self.replication = self.config["replication"]
        if self.replication != 3:
            raise Exception("only replication factor of 3 is supported wit tx-money scenario")
        self.partitions = self.config["partitions"]
        self.config["experiment_id"] = experiment_id
        self.config["result"] = Result.PASSED
        chaos_logger.info(f"starting experiment {self.config['name']} (id={self.config['experiment_id']})")
        
        mkdir("-p", f"/mnt/vectorized/experiments/{self.config['experiment_id']}")

        tasks_logger.info(f"stopping workload everywhere (if running)")
        wait_all_workloads_killed("/mnt/vectorized/client.nodes")

        self.workload_cluster = WORKLOADS[self.config["workload"]["name"]]("/mnt/vectorized/client.nodes")
        chaos_logger.info(f"undoing clients faults")
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
        
        chaos_logger.info(f"undoing redpanda faults")
        self.redpanda_cluster.heal()

        tasks_logger.info(f"(re-)starting fresh redpanda cluster")
        self.redpanda_cluster.kill_everywhere()
        self.redpanda_cluster.wait_killed(timeout_s=10)
        self.redpanda_cluster.clean_everywhere()

        for host in self.redpanda_cluster.hosts:
            node_id = self.redpanda_cluster.get_id()
            if host == self.redpanda_cluster.hosts[0]:
                self.redpanda_cluster.add_seed(host, node_id)
            else:
                self.redpanda_cluster.add_node(host, node_id)

        tx_log_level = self.read_config(["settings", "log-level", "tx"], "info")

        self.redpanda_cluster.launch_everywhere(self.read_config(["settings", "redpanda"], {}), tx_log_level=tx_log_level)
        self.redpanda_cluster.wait_alive(timeout_s=10)
        self.redpanda_cluster.get_stable_view(timeout_s=60)

        sleep(5)
        # waiting for the controller to be up before creating a topic
        tasks_logger.info(f"waiting for the controller to be online")
        self.redpanda_cluster.wait_leader("controller", namespace="redpanda", replication=len(self.redpanda_cluster.nodes), timeout_s=30)

        chaos_logger.info(f"creating \"{self.source}\" topic with replication factor {self.replication} & {self.partitions} partitions")
        self.redpanda_cluster.create_topic(self.source, self.replication, self.partitions)
        chaos_logger.info(f"creating \"{self.target}\" topic with replication factor {self.replication}")
        self.redpanda_cluster.create_topic(self.target, self.replication, 1)

        # waiting for the topic to come online
        tasks_logger.info(f"waiting for topic {self.target} to have leader")
        self.redpanda_cluster.wait_leader(self.target, replication=self.replication, timeout_s=20)
        for partition in range(0, self.partitions):
            tasks_logger.info(f"waiting for topic {self.source}/{partition} to have leader")
            self.redpanda_cluster.wait_leader(self.source, partition=partition, replication=self.replication, timeout_s=20)

        chaos_logger.info(f"launching workload service")
        self.workload_cluster.launch_everywhere()
        self.workload_cluster.wait_alive(timeout_s=10)
        sleep(5)
        self.workload_cluster.wait_ready(timeout_s=10)

        servers = [x.ip for x in self.workload_cluster.nodes]
        servers.sort()
        for node in self.workload_cluster.nodes:
            chaos_logger.info(f"init workload with brokers=\"{self.redpanda_cluster.brokers()}\", source=\"{self.source}\", target=\"{self.target}\" & group_ip=\"{self.config['group_id']}\" on {node.ip}")
            self.workload_cluster.init(servers.index(node.ip), node, node.ip, self.redpanda_cluster.brokers(), self.source, self.partitions, self.target, self.config['group_id'], self.config['experiment_id'], self.config["workload"]["settings"])

        for node in self.workload_cluster.nodes:
            chaos_logger.info(f"starting workload on {node.ip}")
            self.workload_cluster.start(node)
        
        ### distributing internal and data topic across different nodes
        wait_progress_timeout_s = self.read_config(["settings", "setup", "wait_progress_timeout_s"], 20)
        
        tasks_logger.info(f"waiting for initial progress")
        try:
            self.workload_cluster.wait_progress(timeout_s=wait_progress_timeout_s)
        except TimeoutException:
            raise ProgressException()
        tasks_logger.info(f"waiting for id_allocator to have leader")
        self.redpanda_cluster.wait_leader("id_allocator", namespace="kafka_internal", replication=3, timeout_s=10)
        tasks_logger.info(f"waiting for tx coordinator to have leader")
        self.redpanda_cluster.wait_leader("tx", namespace="kafka_internal", replication=3, timeout_s=10)
        tasks_logger.info(f"waiting for consumer groups to have leader")
        self.redpanda_cluster.wait_leader("__consumer_offsets", namespace="kafka", replication=3, timeout_s=10)

        chaos_logger.info(f"warming up for 20s")
        sleep(20)

        internal_nodes = self.redpanda_cluster.nodes[0:3]
        data_nodes = self.redpanda_cluster.nodes[3:]

        # reconfigure id_allocator to use internal_nodes
        tasks_logger.info(f"reconfigure id_allocator")
        self._reconfigure(internal_nodes, "id_allocator", partition=0, namespace="kafka_internal", timeout_s=20)
        # reconfigure tx to use internal_nodes
        tasks_logger.info(f"reconfigure tx coordinator")
        self._reconfigure(internal_nodes, "tx", partition=0, namespace="kafka_internal", timeout_s=20)
        # reconfigure consumer groups to use internal_nodes
        tasks_logger.info(f"reconfigure consumer groups")
        self._reconfigure(internal_nodes, "__consumer_offsets", partition=0, namespace="kafka", timeout_s=20)

        tasks_logger.info(f"reconfigure topic {self.target}")
        self._reconfigure(data_nodes, self.target, partition=0, namespace="kafka", timeout_s=20)
        for partition in range(0, self.partitions):
            tasks_logger.info(f"reconfigure topic {self.source}/{partition}")
            self._reconfigure(data_nodes, self.source, partition=partition, namespace="kafka", timeout_s=20)
        
        tasks_logger.info(f"waiting for post reconfigure progress")
        try:
            self.workload_cluster.wait_progress(timeout_s=wait_progress_timeout_s)
        except TimeoutException:
            raise ProgressException()

        tasks_logger.info(f"transfer controller leadership to {internal_nodes[0].id}")
        self._transfer(internal_nodes[0], "controller", partition=0, namespace="redpanda", timeout_s=20)
        tasks_logger.info(f"transfer id_allocator leadership to {internal_nodes[1].id}")
        self._transfer(internal_nodes[1], "id_allocator", partition=0, namespace="kafka_internal", timeout_s=20)
        tasks_logger.info(f"transfer consumer group leadership to {internal_nodes[1].id}")
        self._transfer(internal_nodes[1], "__consumer_offsets", partition=0, namespace="kafka", timeout_s=20)
        tasks_logger.info(f"transfer tx coordinator leadership to {internal_nodes[2].id}")
        self._transfer(internal_nodes[2], "tx", partition=0, namespace="kafka_internal", timeout_s=20)

        tasks_logger.info(f"transfer topic {self.target} leadership to {data_nodes[0].id}")
        self._transfer(data_nodes[0], self.target, partition=0, namespace="kafka", timeout_s=20)

        for partition in range(0, self.partitions):
            tasks_logger.info(f"transfer topic {self.source}/{partition} leadership to {data_nodes[partition%len(data_nodes)].id}")
            self._transfer(data_nodes[partition%len(data_nodes)], self.source, partition=partition, namespace="kafka", timeout_s=20)

        tasks_logger.info(f"waiting for post transfer progress")
        try:
            self.workload_cluster.wait_progress(timeout_s=wait_progress_timeout_s)
        except TimeoutException:
            raise ProgressException()
        warmup_s = self.read_config(["settings", "setup", "warmup_s"], 20)
        if warmup_s > 0:
            chaos_logger.info(f"warming up for {warmup_s}s")
            sleep(warmup_s)