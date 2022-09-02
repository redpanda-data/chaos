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
        tx_log_level = scenario.read_config(["settings", "log-level", "tx"], "info")
        for replica in scenario.redpanda_cluster.nodes:
            ssh("ubuntu@"+replica.ip, "/mnt/vectorized/control/redpanda.start.sh", tx_log_level)