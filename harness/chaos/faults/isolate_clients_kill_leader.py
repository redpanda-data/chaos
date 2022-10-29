from time import sleep
from sh import ssh
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class IsolateClientsKillLeader:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.name = "isolate clients / kill leader"
        self.leader = None
        self.fault_config = fault_config
    
    def inject(self, scenario):
        self.leader = scenario.redpanda_cluster.wait_leader(scenario.topic, partition=scenario.partition, timeout_s=10)
        logger.debug(f"isolating clients from redpanda cluster")

        redpanda_nodes = []
        for node in scenario.redpanda_cluster.nodes:
            redpanda_nodes.append(node.ip)
        
        for node in scenario.workload_cluster.nodes:
            ssh("ubuntu@"+node.ip, "/mnt/vectorized/control/network.isolate.sh", *redpanda_nodes)
        
        sleep(self.fault_config["kill_delay_s"])

        self.leader = scenario.redpanda_cluster.wait_leader(scenario.topic, partition=scenario.partition, timeout_s=10)
        logger.debug(f"killing {scenario.topic}'s leader: {self.leader.ip}")
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/redpanda.stop.sh")

        sleep(self.fault_config["reconnect_delay_s"])

        logger.debug(f"reconnecting clients to redpanda cluster")
        for node in scenario.workload_cluster.nodes:
            ssh("ubuntu@"+node.ip, "/mnt/vectorized/control/network.heal.sh", *redpanda_nodes)
    
    def heal(self, scenario):
        default = scenario.default_log_level()
        log_levels = scenario.log_levels()
        ssh("ubuntu@"+self.leader.ip, "/mnt/vectorized/control/redpanda.start.sh", default, log_levels)