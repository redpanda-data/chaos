from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class KillPartitionFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.replicas = []
        self.name = "kill partition"
        self.fault_config = fault_config

    def inject(self, scenario):
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

        self.replicas = replicas_info.replicas

        for replica in self.replicas:
            logger.debug(f"killing {namespace}/{topic}/{partition}'s node: {replica.ip}")
            ssh("ubuntu@"+replica.ip, "/mnt/vectorized/control/redpanda.stop.sh")
    
    def heal(self, scenario):
        tx_log_level = scenario.read_config(["settings", "log-level", "tx"], "info")
        for replica in self.replicas:
            ssh("ubuntu@"+replica.ip, "/mnt/vectorized/control/redpanda.start.sh", tx_log_level)