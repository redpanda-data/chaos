from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class IsolateAllFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.name = "isolate all"

    def inject(self, scenario):
        nodes = []
        for node in scenario.redpanda_cluster.nodes:
            nodes.append(node.ip)
        for node in nodes:
            rest = list(filter(lambda x: x != node, nodes))
            logger.debug(f"isolating {node} from redpanda cluster")
            ssh("ubuntu@"+node, "/mnt/vectorized/control/network.isolate.sh", *rest)
    
    def heal(self, scenario):
        nodes = []
        for node in scenario.redpanda_cluster.nodes:
            nodes.append(node.ip)
        for node in nodes:
            rest = list(filter(lambda x: x != node, nodes))
            logger.debug(f"reconnecting {node} with the redpanda cluster")
            ssh("ubuntu@"+node, "/mnt/vectorized/control/network.heal.sh", *rest)