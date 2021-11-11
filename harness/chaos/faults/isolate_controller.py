from time import sleep
from sh import ssh
import logging

logger = logging.getLogger("chaos")

class IsolateControllerFault:
    def __init__(self):
        self.fault_type = "RECOVERABLE"
        self.follower = None
        self.rest = []
        self.name = "isolate controller (topic's follower)"
    
    def export(self):
        return {
            "follower": self.follower,
            "rest": self.rest
        }
    
    def load(self, data):
        self.follower = data["follower"]
        self.rest = data["rest"]

    def inject(self, scenario):
        self.follower = None
        self.rest = []
        
        controller_leader = None
        while controller_leader == None:
            logger.debug("getting controller leader")
            controller_leader = scenario.redpanda_cluster.get_leader("controller", 0, namespace="redpanda")
            if controller_leader == None:
                sleep(1)
        logger.debug(f"controller leader: {controller_leader}")
        
        leader = None
        while leader == None:
            leader = scenario.redpanda_cluster.get_leader(scenario.topic, scenario.partition)
            if leader == None:
                sleep(1)
        logger.debug("leader: " + leader)

        if leader == controller_leader:
            raise Exception(f"controller leader ({controller_leader}) can't match topic's leader ({leader})")

        self.follower = controller_leader

        for node in scenario.redpanda_cluster.nodes:
            if self.follower != node.ip:
                self.rest.append(node.ip)
        ssh("ubuntu@"+self.follower, "/mnt/vectorized/control/network.isolate.sh", *self.rest)
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.follower, "/mnt/vectorized/control/network.heal.sh", *self.rest)