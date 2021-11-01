from time import sleep
import logging

logger = logging.getLogger("chaos")

class LeadershipTransferFault:
    def __init__(self):
        self.fault_type = "ONEOFF"
        self.name = "leadership transfer"
    
    def export(self):
        return {}

    def execute(self, scenario):
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

        follower = None
        for node in scenario.redpanda_cluster.nodes:
            if node.ip == leader:
                continue
            elif node.ip == controller_leader:
                continue
            else:
                follower = node
                break

        scenario.redpanda_cluster.transfer_leadership_to(follower, "kafka", scenario.topic, scenario.partition, scenario.replication)