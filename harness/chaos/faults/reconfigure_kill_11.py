import time
import logging
from sh import ssh
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class ReconfigureKill11Fault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.name = "kill during reconfiguration (1 -> 1)"
        self.new_leader = None
        self.fault_config = fault_config

    def inject(self, scenario):
        controller = scenario.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=10)
        logger.debug(f"controller's leader: {controller.ip}")
        
        replicas_info = scenario.redpanda_cluster.wait_details(scenario.topic, partition=scenario.partition, timeout_s=10)
        if len(replicas_info.replicas)!=1:
            raise Exception(f"topic {scenario.topic} doesn't have replication factor of 1")
        leader = replicas_info.leader

        for replica in scenario.redpanda_cluster.nodes:
            if replica == leader:
                continue
            if replica == controller:
                continue
            self.new_leader = replica
        
        logger.debug(f"reconfiguring {scenario.topic} from {leader.ip} to {self.new_leader.ip}")
        scenario.redpanda_cluster.reconfigure(leader, [self.new_leader], scenario.topic, partition=scenario.partition)
        logger.debug(f"killing {scenario.topic}'s new leader {self.new_leader.ip}")
        ssh("ubuntu@"+self.new_leader.ip, "/mnt/vectorized/control/redpanda.stop.sh")
        logger.debug(f"killed {scenario.topic}'s new leader {self.new_leader.ip}")

    def heal(self, scenario):
        logger.debug(f"healing {scenario.topic}'s new leader {self.new_leader.ip}")
        ssh("ubuntu@"+self.new_leader.ip, "/mnt/vectorized/control/redpanda.start.sh")
        timeout_s = self.fault_config["timeout_s"]
        begin = time.time()
        while True:
            if time.time() - begin > timeout_s:
                raise TimeoutException(f"can't reconfigure {scenario.topic} within {timeout_s} sec after healing {self.new_leader.ip}")
            replicas_info = scenario.redpanda_cluster.wait_details(scenario.topic, partition=scenario.partition, timeout_s=timeout_s)
            if replicas_info.leader == self.new_leader and replicas_info.status == "done" and len(replicas_info.replicas)==1:
                break
            time.sleep(1)
        logger.debug(f"reconfigured {scenario.topic} to [{self.new_leader.ip}]")
