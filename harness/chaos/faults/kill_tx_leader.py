from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class KillTxLeaderFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.leader = None
        self.name = "kill tx coordinator's leader"

    def inject(self, scenario):
        self.leader = scenario.redpanda_cluster.wait_leader("tx", partition=0, namespace="kafka_internal", timeout_s=10)
        logger.debug(f"killing tx coordinator's leader: {self.leader.ip}")
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/redpanda.stop.sh")
    
    def heal(self, scenario):
        default = scenario.default_log_level()
        log_levels = scenario.log_levels()
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/redpanda.start.sh", default, log_levels)
