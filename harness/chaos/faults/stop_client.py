from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class StopClient:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.name = "stop client"
        self.client = None
        self.fault_config = fault_config
    
    def inject(self, scenario):
        self.client = scenario.workload_cluster.nodes[0]
        logger.debug(f"stopping client {self.client.ip}")
        scenario.workload_cluster.pause(self.client)
    
    def heal(self, scenario):
        logger.debug(f"restarting client {self.client.ip}")
        scenario.workload_cluster.resume(self.client)