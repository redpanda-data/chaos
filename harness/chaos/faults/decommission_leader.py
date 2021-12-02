from time import sleep
import time
from sh import ssh
import logging
import json
from chaos.faults.types import FaultType
from chaos.redpanda_cluster import TimeoutException

logger = logging.getLogger("chaos")

def _denoise(brokers):
    r = []
    for broker in brokers:
        r.append({
            "node_id": broker["node_id"],
            "membership_status": broker["membership_status"],
            "is_alive": broker["is_alive"],
        })
    return r

class DecommissionLeaderFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.ONEOFF
        self.name = "decommissioning leader"
    
    def execute(self, scenario):
        timeout_s = 60
        
        leader = scenario.redpanda_cluster.wait_leader(scenario.topic, partition=scenario.partition, replication=scenario.replication, timeout_s=timeout_s)
        logger.debug(f"decommissioning {scenario.topic}'s leader: ip:{leader.ip} id:{leader.id}")

        survivors = []
        survivors_id = set()

        for node in scenario.redpanda_cluster.nodes:
            if node != leader:
                survivors.append(node)
                survivors_id.add(node.id)
        
        scenario.redpanda_cluster.admin_decommission(survivors[0], leader)

        begin = time.time()
        decommissioned = False
        while not decommissioned:
            if time.time() - begin > timeout_s:
                raise TimeoutException(f"can't decommision {leader.ip} within {timeout_s} sec")
            decommissioned = True
            for node in survivors:
                brokers = _denoise(scenario.redpanda_cluster.admin_brokers(node))
                if len(brokers) != len(survivors):
                    decommissioned = False
                for broker in brokers:
                    if broker["node_id"] not in survivors_id:
                        decommissioned = False