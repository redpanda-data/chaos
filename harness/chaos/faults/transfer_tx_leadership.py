from time import sleep
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class TransferTxLeadershipFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.ONEOFF
        self.name = "transfer tx leadership"

    def execute(self, scenario):
        id_allocator = scenario.redpanda_cluster.wait_leader("id_allocator", namespace="kafka_internal", timeout_s=10)
        logger.debug(f"kafka_internal/id_allocator/0's leader: {id_allocator.ip}")
        
        tx_info = scenario.redpanda_cluster.wait_details("tx", partition=0, namespace="kafka_internal", timeout_s=10)
        if len(tx_info.replicas)==1:
            raise Exception(f"kafka_internal/tx/0 has replication factor of 1: can't find a follower")

        follower = None
        for replica in tx_info.replicas:
            if replica == tx_info.leader:
                continue
            if follower == None:
                follower = replica
            if replica != id_allocator:
                follower = replica

        logger.debug(f"tranferring kafka_internal/tx/0's leadership from {tx_info.leader.ip} to {follower.ip}")
        scenario.redpanda_cluster.transfer_leadership_to(follower, "kafka_internal", "tx", 0)