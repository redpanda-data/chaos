import time
import logging
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class Reconfigure313Fault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.name = "reconfiguration (3 -> 1 -> 3)"
        self.fault_config = fault_config

    def inject(self, scenario):
        controller = scenario.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=10)
        logger.debug(f"controller's leader: {controller.ip}")
        
        replicas_info = scenario.redpanda_cluster.wait_details(scenario.topic, partition=scenario.partition, timeout_s=10)
        if len(replicas_info.replicas)!=3:
            raise Exception(f"topic {scenario.topic} doesn't have replication factor of 3")
        leader = replicas_info.leader

        new_leader = None
        for replica in scenario.redpanda_cluster.nodes:
            if replica == leader:
                continue
            if replica == controller:
                continue
            new_leader = replica
        
        timeout_s = self.fault_config["timeout_s"]
        begin = time.time()
        logger.debug(f"reconfiguring {scenario.topic} to [{new_leader.ip}]")
        scenario.redpanda_cluster.reconfigure(leader, [new_leader], scenario.topic, partition=scenario.partition)
        while True:
            if time.time() - begin > timeout_s:
                raise TimeoutException(f"can't reconfigure {scenario.topic} within {timeout_s} sec")
            replicas_info = scenario.redpanda_cluster.wait_details(scenario.topic, partition=scenario.partition, timeout_s=timeout_s)
            if replicas_info.leader == new_leader and replicas_info.status == "done" and len(replicas_info.replicas)==1:
                break
            time.sleep(1)
        logger.debug(f"reconfigured {scenario.topic} [{new_leader.ip}]")

    def heal(self, scenario):
        replicas_info = scenario.redpanda_cluster.wait_details(scenario.topic, partition=scenario.partition, timeout_s=10)
        if len(replicas_info.replicas)!=1:
            raise Exception(f"topic {scenario.topic} doesn't have replication factor of 1")
        leader = replicas_info.leader

        replicas = []
        for replica in scenario.redpanda_cluster.nodes:
            if len(replicas) == 3:
                break
            replicas.append(replica)
        
        timeout_s = self.fault_config["timeout_s"]
        begin = time.time()
        logger.debug(f"reconfiguring {scenario.topic} to replication factor of 3")
        scenario.redpanda_cluster.reconfigure(leader, replicas, scenario.topic, partition=scenario.partition)
        while True:
            if time.time() - begin > timeout_s:
                raise TimeoutException(f"can't reconfigure {scenario.topic} within {timeout_s} sec")
            replicas_info = scenario.redpanda_cluster.wait_details(scenario.topic, partition=scenario.partition, timeout_s=timeout_s)
            if replicas_info.status == "done" and len(replicas_info.replicas)==3:
                break
            time.sleep(1)
        logger.debug(f"reconfigured {scenario.topic} to replication factor of 3")