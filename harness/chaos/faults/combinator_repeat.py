from time import sleep
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class RepeatCombinator:
    def __init__(self, FAULTS, fault_config):
        self.fault_type = FaultType.ONEOFF
        self.name = "as oneoff"
        self.fault_config = fault_config
        self.FAULTS = FAULTS

    def execute(self, scenario):
        logger.debug(f"repeating {self.fault_config['subject']['name']} {self.fault_config['times']} times")
        for i in range(0, self.fault_config["times"]):
            if i != 0:
                sleep(self.fault_config["delay_s"])
                scenario.workload_cluster.wait_progress(timeout_s=60)
            logger.debug(f"repeating {self.fault_config['subject']['name']}")
            subject = self.FAULTS[self.fault_config["subject"]["name"]](self.fault_config["subject"])
            subject.execute(scenario)