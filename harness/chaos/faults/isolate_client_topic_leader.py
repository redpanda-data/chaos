from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class IsolateClientTopicLeader:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.name = "isolate client & topic leader"
        self.client = None
        self.leader = None
        self.fault_config = fault_config
    
    def inject(self, scenario):
        self.client = scenario.workload_cluster.nodes[0]

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
        self.leader = scenario.redpanda_cluster.wait_leader(topic, partition=partition, namespace=namespace, timeout_s=10)
        logger.debug(f"isolating client {self.client.ip} from {namespace}/{topic}/{partition}'s leader: {self.leader.ip}")
        
        ssh("ubuntu@"+self.client.ip, "/mnt/vectorized/control/network.isolate.sh", self.leader.ip)
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.client.ip, "/mnt/vectorized/control/network.heal.sh", self.leader.ip)