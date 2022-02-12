from random import Random
from itsdangerous import json
from time import sleep
import sys
import time
from random import Random
import traceback
import logging
from chaos.types import TimeoutException
from chaos.faults.types import FaultType

logger = logging.getLogger("chaos")

class LeadershipTransferFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.ONEOFF
        self.name = "leadership transfer"
        self.fault_config = fault_config
        self.random = Random()
    
    def read_config(self, key, default):
        if key in self.fault_config:
            if isinstance(self.fault_config[key], dict):
                if self.fault_config[key]["name"] != "random":
                    raise Exception(f"only random command supported; {json.dumps(self.fault_config[key])}")
                return self.random.choice(self.fault_config[key]["values"])
            else:
                return self.fault_config[key]
        return default()

    def execute(self, scenario):
        timeout_s = 10
        if "timeout_s" in self.fault_config:
            timeout_s = self.fault_config["timeout_s"]
        controller = scenario.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=timeout_s)
        logger.debug(f"controller's leader: {controller.ip}")
        
        topic = self.read_config("topic", lambda: scenario.topic)
        partition = self.read_config("partition", lambda: 0)

        namespace="kafka"
        if "namespace" in self.fault_config:
            namespace = self.fault_config["namespace"]

        replicas_info = scenario.redpanda_cluster.wait_details(topic, partition=partition, namespace=namespace, timeout_s=timeout_s)
        if len(replicas_info.replicas)==1:
            raise Exception(f"topic {namespace}/{topic}/{partition} has replication factor of 1: can't find a follower")

        follower = None
        for replica in replicas_info.replicas:
            if replica == replicas_info.leader:
                continue
            if follower == None:
                follower = replica
            if replica != controller:
                follower = replica
        
        scenario._transfer(follower, topic, partition=partition, namespace=namespace, timeout_s=timeout_s)