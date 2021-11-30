from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class RollingRestartFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.ONEOFF
        self.name = "rolling restart"
        self.fault_config = fault_config

    def execute(self, scenario):
        replicas_info = scenario.redpanda_cluster.wait_details(scenario.topic, partition=scenario.partition, timeout_s=10)
        
        sequence = [ replicas_info.leader.ip ]

        for replica in replicas_info.replicas:
            if replica == replicas_info.leader:
                continue
            sequence.append(replica.ip)
        
        for replica in sequence:
            logger.debug(f"killing {replica}")
            ssh("ubuntu@" + replica, "/mnt/vectorized/control/redpanda.stop.sh")
            logger.debug(f"starting {replica}")
            ssh("ubuntu@" + replica, "/mnt/vectorized/control/redpanda.start.sh")
            if replica != sequence[-1]:
                sleep(self.fault_config["period_s"])