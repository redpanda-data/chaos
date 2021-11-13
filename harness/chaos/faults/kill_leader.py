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

    def inject(self, scenario):
        self.leader = scenario.redpanda_cluster.wait_leader(scenario.topic, partition=scenario.partition, timeout_s=10)
        logger.debug(f"killing {scenario.topic}'s leader: {self.leader.ip}")
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/redpanda.stop.sh")
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/redpanda.start.sh")