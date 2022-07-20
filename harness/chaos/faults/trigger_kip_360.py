from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class TriggerKIP360:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.name = "isolate client from cluster"
        self.redpanda_nodes = None
        self.client = None
        self.fault_config = fault_config
    
    def inject(self, scenario):
        self.client = scenario.workload_cluster.nodes[0]

        scenario.workload_cluster.pause_before_send(self.client)

        # Wait to be sure that client stop before send
        sleep(3)

        scenario.workload_cluster.pause_before_abort(self.client)

        self.redpanda_nodes = []
        for node in scenario.redpanda_cluster.nodes:
            self.redpanda_nodes.append(node.ip)

        ssh("ubuntu@"+self.client.ip, "/mnt/vectorized/control/network.isolate.sh", *self.redpanda_nodes)
        scenario.workload_cluster.resume_before_send(self.client)
    
    def heal(self, scenario):
        ssh("ubuntu@"+self.client.ip, "/mnt/vectorized/control/network.heal.sh", *self.redpanda_nodes)
        scenario.workload_cluster.resume_before_abort(self.client)