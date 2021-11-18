from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class PauseLeaderFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.leader = None
        self.name = "suspending a topic's leader"

    def inject(self, scenario):
        self.leader = scenario.redpanda_cluster.wait_leader(scenario.topic, partition=scenario.partition, timeout_s=10)
        logger.debug(f"suspending {scenario.topic}'s leader: {self.leader.ip}")
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/redpanda.pause.sh")
    
    def heal(self, scenario):
        logger.debug(f"resuming: {self.leader.ip}")
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/redpanda.resume.sh")