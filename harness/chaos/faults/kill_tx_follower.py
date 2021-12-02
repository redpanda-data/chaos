from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class KillTxFollowerFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.follower = None
        self.name = "kill tx coordinator's follower"

    def inject(self, scenario):
        id_allocator = scenario.redpanda_cluster.wait_leader("id_allocator", namespace="kafka_internal", timeout_s=10)
        logger.debug(f"kafka_internal/id_allocator/0's leader: {id_allocator.ip}")
        
        tx_info = scenario.redpanda_cluster.wait_details("tx", partition=0, namespace="kafka_internal", timeout_s=10)
        if len(tx_info.replicas)==1:
            raise Exception(f"kafka_internal/tx/0 has replication factor of 1: can't find a follower")

        self.follower = None
        for replica in tx_info.replicas:
            if replica == tx_info.leader:
                continue
            if self.follower == None:
                self.follower = replica
            if replica != id_allocator:
                self.follower = replica
        
        logger.debug(f"killing kafka_internal/tx/0's follower: {self.follower.ip}")
        ssh("ubuntu@"+self.follower.ip, "/mnt/vectorized/control/redpanda.stop.sh")
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.follower.ip, "/mnt/vectorized/control/redpanda.start.sh")