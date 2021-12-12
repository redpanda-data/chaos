from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class IsolateTxLeaderFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.leader = None
        self.rest = []
        self.name = "isolate tx coordinator's leader"
    
    def inject(self, scenario):
        tx_info = scenario.redpanda_cluster.wait_details("tx", partition=0, namespace="kafka_internal", timeout_s=10)
        self.leader = tx_info.leader
        logger.debug(f"isolating tx coordinator's leader: {self.leader.ip}")

        for node in scenario.redpanda_cluster.nodes:
            if node != self.leader:
                self.rest.append(node.ip)
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/network.isolate.sh", *self.rest)
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/network.heal.sh", *self.rest)