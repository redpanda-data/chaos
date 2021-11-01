from time import sleep
from sh import ssh
import logging

logger = logging.getLogger("chaos")

class IsolateLeaderFault:
    def __init__(self):
        self.fault_type = "RECOVERABLE"
        self.leader = None
        self.followers = None
        self.name = "isolate leader"
    
    def export(self):
        return {
            "leader": self.leader,
            "followers": self.followers
        }
    
    def load(self, data):
        self.leader = data["leader"]
        self.followers = data["followers"]

    def inject(self, scenario):
        self.leader = None
        self.followers = []
        while self.leader == None:
            self.leader = scenario.redpanda_cluster.get_leader(scenario.topic, scenario.replication, scenario.partition)
            if self.leader == None:
                sleep(1)
        logger.debug("leader: " + self.leader)
        for node in scenario.redpanda_cluster.nodes:
            if node.ip != self.leader:
                self.followers.append(node.ip)
        ssh("ubuntu@"+self.leader, "/mnt/vectorized/control/network.isolate.sh", *self.followers)
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.leader, "/mnt/vectorized/control/network.heal.sh", *self.followers)