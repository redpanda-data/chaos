from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class IsolateControllerFault:
    def __init__(self):
        self.fault_type = FaultType.RECOVERABLE
        self.controller = None
        self.rest = []
        self.name = "isolate controller"

    def inject(self, scenario):
        self.controller = scenario.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=10)
        logger.debug(f"controller's leader: {self.controller.ip}")

        for node in scenario.redpanda_cluster.nodes:
            if self.controller != node:
                self.rest.append(node.ip)
        ssh("ubuntu@"+self.controller.ip, "/mnt/vectorized/control/network.isolate.sh", *self.rest)
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.controller.ip, "/mnt/vectorized/control/network.heal.sh", *self.rest)