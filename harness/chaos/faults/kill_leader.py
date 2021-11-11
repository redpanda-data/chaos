from time import sleep
from sh import ssh
import logging

logger = logging.getLogger("chaos")

class KillLeaderFault:
    def __init__(self):
        self.fault_type = "RECOVERABLE"
        self.leader = None
        self.name = "kill a topic's leader"
    
    def export(self):
        return {
            "leader": self.leader
        }
    
    def load(self, data):
        self.leader = data["leader"]

    def inject(self, scenario):
        self.leader = None
        while self.leader == None:
            self.leader = scenario.redpanda_cluster.get_leader(scenario.topic, scenario.partition)
            if self.leader == None:
                sleep(1)
        logger.debug("leader: " + self.leader)
        ssh("ubuntu@"+self.leader, "/mnt/vectorized/control/redpanda.stop.sh")
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.leader, "/mnt/vectorized/control/redpanda.start.sh")