from time import sleep
from sh import ssh
import logging

logger = logging.getLogger("chaos")

class KillFollowerFault:
    def __init__(self):
        self.fault_type = "RECOVERABLE"
        self.follower = None
        self.name = "kill a topic's follower"
    
    def export(self):
        return {
            "follower": self.follower
        }
    
    def load(self, data):
        self.follower = data["follower"]

    def inject(self, scenario):
        self.follower = None
        
        controller_leader = None
        while controller_leader == None:
            logger.debug("getting controller leader")
            controller_leader = scenario.redpanda_cluster.get_leader("controller", 3, 0, namespace="redpanda")
            if controller_leader == None:
                sleep(1)
        logger.debug(f"controller leader: {controller_leader}")
        
        leader = None
        while leader == None:
            leader = scenario.redpanda_cluster.get_leader(scenario.topic, scenario.replication, scenario.partition)
            if leader == None:
                sleep(1)
        logger.debug("leader: " + leader)

        if leader == controller_leader:
            raise Exception(f"controller leader ({controller_leader}) can't match topic's leader ({leader})")
        
        for node in scenario.redpanda_cluster.nodes:
            if node.ip == leader:
                continue
            elif node.ip == controller_leader:
                continue
            else:
                self.follower = node.ip
                break
        logger.debug("follower: " + self.follower)
        ssh("ubuntu@"+self.follower, "/mnt/vectorized/control/redpanda.stop.sh")
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.follower, "/mnt/vectorized/control/redpanda.start.sh")