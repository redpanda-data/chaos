from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class PauseAllFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.ONEOFF
        self.name = "suspending redpanda"
        self.fault_config = fault_config

    def execute(self, scenario):
        repeats = 1
        if "repeats" in self.fault_config:
            repeats = self.fault_config["repeats"]
        for i in range(0,repeats):
            if i!=0:
                sleep(5)
                scenario.workload_cluster.wait_progress(timeout_s=60)
            for node in scenario.redpanda_cluster.nodes:
                logger.debug(f"suspending {node.ip}")
                ssh("ubuntu@"+node.ip, "/mnt/vectorized/control/redpanda.pause.sh")
            logger.debug(f"sleeping for 5s")
            sleep(5)
            for node in scenario.redpanda_cluster.nodes:
                logger.debug(f"resuming {node.ip}")
                ssh("ubuntu@"+node.ip, "/mnt/vectorized/control/redpanda.resume.sh")