from time import sleep
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class AsOneoffCombinator:
    def __init__(self, FAULTS, fault_config):
        self.fault_type = FaultType.ONEOFF
        self.name = "as oneoff"
        self.fault_config = fault_config
        self.FAULTS = FAULTS

    def execute(self, scenario):
        logger.debug(f"wrap {self.fault_config['subject']['name']} as oneoff")
        subject = self.FAULTS[self.fault_config["subject"]["name"]](self.fault_config["subject"])
        subject.inject(scenario)
        sleep(self.fault_config["delay_s"])
        subject.heal(scenario)