from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class IsolateTxAllFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.name = "isolate tx all"
        self.data_nodes = []
        self.tx_nodes = []

    def inject(self, scenario):
        tx_info = scenario.redpanda_cluster.wait_details("tx", partition=0, namespace="kafka_internal", timeout_s=10)
        tx_node_ids = set(map(lambda x: x.id, tx_info.replicas))
        self.data_nodes = []
        self.tx_nodes = []
        for node in scenario.redpanda_cluster.nodes:
            if node.id in tx_node_ids:
                self.tx_nodes.append(node.ip)
            self.data_nodes.append(node.ip)
        for node in self.data_nodes:
            logger.debug(f"isolating {node} from tx coordinator")
            ssh("ubuntu@"+node, "/mnt/vectorized/control/network.isolate.sh", *self.tx_nodes)
    
    def heal(self, scenario):
        nodes = []
        for node in scenario.redpanda_cluster.nodes:
            nodes.append(node.ip)
        for node in nodes:
            logger.debug(f"reconnecting {node} with tx coordinator")
            ssh("ubuntu@"+node, "/mnt/vectorized/control/network.heal.sh", *self.tx_nodes)