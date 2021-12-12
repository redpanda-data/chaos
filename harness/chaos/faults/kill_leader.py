from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class KillLeaderFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.leader = None
        self.name = "kill a topic's leader"
        self.fault_config = fault_config

    def inject(self, scenario):
        topic = None
        if "topic" in self.fault_config:
            topic = self.fault_config["topic"]
        else:
            topic = scenario.topic
        self.leader = scenario.redpanda_cluster.wait_leader(topic, partition=scenario.partition, timeout_s=10)
        logger.debug(f"killing {topic}'s leader: {self.leader.ip}")
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/redpanda.stop.sh")
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/redpanda.start.sh")