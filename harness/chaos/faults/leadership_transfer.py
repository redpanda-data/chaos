from time import sleep
import logging

logger = logging.getLogger("chaos")

class LeadershipTransferFault:
    def __init__(self):
        self.fault_type = "ONEOFF"
        self.name = "leadership transfer"

    def execute(self, scenario):
        controller = scenario.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=10)
        logger.debug(f"controller's leader: {controller.ip}")
        
        replicas_info = scenario.redpanda_cluster.wait_replicas(scenario.topic, partition=scenario.partition, timeout_s=10)
        if len(replicas_info.replicas)==1:
            raise Exception(f"topic {scenario.topic} has replication factor of 1: can't find a follower")

        follower = None
        for replica in replicas_info.replicas:
            if replica == replicas_info.leader:
                continue
            if follower == None:
                follower = replica
            if replica != controller:
                follower = replica
        
        logger.debug(f"tranferring {scenario.topic}'s leadership from {replicas_info.leader.ip} to {follower.ip}")
        scenario.redpanda_cluster.transfer_leadership_to(follower, "kafka", scenario.topic, scenario.partition)