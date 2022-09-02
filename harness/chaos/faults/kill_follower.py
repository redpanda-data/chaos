from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class KillFollowerFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.follower = None
        self.fault_config = fault_config
        self.name = "kill a topic's follower"

    def inject(self, scenario):
        controller = scenario.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=10)
        logger.debug(f"controller's leader: {controller.ip}")
        
        topic = None
        if "topic" in self.fault_config:
            topic = self.fault_config["topic"]
        else:
            topic = scenario.topic
        partition = 0
        if "partition" in self.fault_config:
            partition = self.fault_config["partition"]
        else:
            partition = scenario.partition
        namespace="kafka"
        if "namespace" in self.fault_config:
            namespace = self.fault_config["namespace"]

        replicas_info = scenario.redpanda_cluster.wait_details(topic, partition=partition, namespace=namespace, timeout_s=10)
        if len(replicas_info.replicas)==1:
            raise Exception(f"topic {scenario.topic} has replication factor of 1: can't find a follower")

        self.follower = None
        for replica in replicas_info.replicas:
            if replica == replicas_info.leader:
                continue
            if self.follower == None:
                self.follower = replica
            if replica != controller:
                self.follower = replica
        
        logger.debug(f"killing {namespace}/{topic}/{partition}'s follower: {self.follower.ip}")
        ssh("ubuntu@"+self.follower.ip, "/mnt/vectorized/control/redpanda.stop.sh")
    
    def heal(self, scenario):
        tx_log_level = scenario.read_config(["settings", "log-level", "tx"], "info")
        ssh("ubuntu@"+self.follower.ip, "/mnt/vectorized/control/redpanda.start.sh", tx_log_level)