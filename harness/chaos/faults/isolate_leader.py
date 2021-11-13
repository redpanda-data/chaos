from time import sleep
from sh import ssh
import logging

logger = logging.getLogger("chaos")

class IsolateLeaderFault:
    def __init__(self):
        self.fault_type = "RECOVERABLE"
        self.leader = None
        self.rest = []
        self.name = "isolate leader"
    
    def inject(self, scenario):
        self.leader = scenario.redpanda_cluster.wait_leader(scenario.topic, partition=scenario.partition, timeout_s=10)
        logger.debug(f"isolating {scenario.topic}'s leader: {self.leader.ip}")

        for node in scenario.redpanda_cluster.nodes:
            if node != self.leader:
                self.rest.append(node.ip)
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/network.isolate.sh", *self.rest)
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/network.heal.sh", *self.rest)