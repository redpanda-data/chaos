from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class KillAllFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.name = "kill all nodes"

    def inject(self, scenario):
        for replica in scenario.redpanda_cluster.nodes:
            ssh("ubuntu@"+replica.ip, "/mnt/vectorized/control/redpanda.stop.sh")
    
    def heal(self, scenario):
        default = scenario.default_log_level()
        log_levels = scenario.log_levels()
        for replica in scenario.redpanda_cluster.nodes:
            ssh("ubuntu@"+replica.ip, "/mnt/vectorized/control/redpanda.start.sh", default, log_levels)