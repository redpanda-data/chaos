import time
import logging
from chaos.faults.types import FaultType
from chaos.types import TimeoutException

logger = logging.getLogger("chaos")

class Reconfigure313Fault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.RECOVERABLE
        self.name = "reconfiguration (3 -> 1 -> 3)"
        self.fault_config = fault_config
        self.old_replicas = None

    def inject(self, scenario):
        timeout_s = self.fault_config["timeout_s"]
        controller = scenario.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=timeout_s)
        logger.debug(f"controller's leader: {controller.ip}")
        
        topic = None
        if "topic" in self.fault_config:
            topic = self.fault_config["topic"]
        else:
            topic = scenario.topic
        partition = 0
        if "partition" in self.fault_config:
            partition = self.fault_config["partition"]
        else:
            partition = scenario.partition
        namespace="kafka"
        if "namespace" in self.fault_config:
            namespace = self.fault_config["namespace"]

        replicas_info = scenario.redpanda_cluster.wait_details(topic, partition=partition, namespace=namespace, timeout_s=timeout_s)
        if len(replicas_info.replicas)!=3:
            raise Exception(f"topic {topic} doesn't have replication factor of 3")

        new_leader = None
        old_leader = replicas_info.leader
        self.old_replicas = set(replicas_info.replicas)

        candidates = []
        for node in scenario.redpanda_cluster.nodes:
            if node == replicas_info.leader:
                continue
            if node == controller:
                continue
            candidates.append(node)
        
        for node in candidates:
            if node not in self.old_replicas:
                new_leader = node
        
        if new_leader == None:
            new_leader = candidates[0]
        
        begin = time.time()
        logger.debug(f"reconfiguring {namespace}/{topic}/{partition} to {new_leader.id} ({new_leader.ip})")
        scenario.redpanda_cluster.reconfigure(controller, [new_leader], topic, partition=partition, namespace=namespace)
        while True:
            if time.time() - begin > timeout_s:
                raise TimeoutException(f"can't reconfigure {topic} within {timeout_s} sec")
            replicas_info = scenario.redpanda_cluster.wait_details(topic, partition=partition, namespace=namespace, timeout_s=timeout_s)
            if replicas_info.leader != old_leader:
                break
            logger.debug(f"isn't reconfigured status={replicas_info.status} leader={replicas_info.leader.id} len(replicas)={len(replicas_info.replicas)}")
            time.sleep(1)
        
        logger.debug(f"reconfigured {namespace}/{topic}/{partition} to [{','.join(map(lambda x:x.ip, replicas_info.replicas))}]")

    def heal(self, scenario):
        timeout_s = self.fault_config["timeout_s"]
        controller = scenario.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=timeout_s)
        logger.debug(f"controller's leader: {controller.ip}")

        topic = None
        if "topic" in self.fault_config:
            topic = self.fault_config["topic"]
        else:
            topic = scenario.topic
        partition = 0
        if "partition" in self.fault_config:
            partition = self.fault_config["partition"]
        else:
            partition = scenario.partition
        namespace="kafka"
        if "namespace" in self.fault_config:
            namespace = self.fault_config["namespace"]

        replicas = list(self.old_replicas)
        
        timeout_s = self.fault_config["timeout_s"]
        begin = time.time()
        logger.debug(f"reconfiguring {namespace}/{topic}/{partition} to replication factor of 3")
        scenario.redpanda_cluster.reconfigure(controller, replicas, topic, partition=partition, namespace=namespace)
        while True:
            if time.time() - begin > timeout_s:
                raise TimeoutException(f"can't reconfigure {namespace}/{topic}/{partition} within {timeout_s} sec")
            replicas_info = scenario.redpanda_cluster.wait_details(topic, partition=partition, namespace=namespace, timeout_s=timeout_s)
            if replicas_info.status == "done" and len(replicas_info.replicas)==3:
                break
            logger.debug(f"isn't reconfigured status={replicas_info.status} len(replicas)={len(replicas_info.replicas)}")
            time.sleep(1)
        logger.debug(f"reconfigured {namespace}/{topic}/{partition} to replication factor of 3")