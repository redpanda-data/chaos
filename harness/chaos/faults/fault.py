from abc import ABC

from chaos.faults.types import FaultType

class Fault(ABC):
    def __init__(self, fault_type, fault_config):
        self.fault_type = fault_type
        self.fault_config = fault_config
    
    def read_config(self, path, default):
        root = self.fault_config
        for node in path:
            if node not in root:
                return default
            root = root[node]
        return root

class RecoverableFault(Fault):
    def __init__(self, fault_config):
        super().__init__(FaultType.RECOVERABLE, fault_config)