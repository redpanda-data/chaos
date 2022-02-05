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

    def execute(self, scenario):
        timeout_s = 10
        if "timeout_s" in self.fault_config:
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
            if isinstance(self.fault_config["partition"], dict):
                if self.fault_config["partition"]["name"] != "random":
                    raise Exception(f"only random command supported; {json.dumps(self.fault_config['partition'])}")
                partition = self.random.randrange(0, self.fault_config["partition"]["supremum"])
            else:
                partition = self.fault_config["partition"]
        else:
            partition = scenario.partition
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
        
        logger.debug(f"tranferring {namespace}/{topic}/{partition}'s leadership from {replicas_info.leader.ip} to {follower.ip}")
        
        begin = time.time()
        while True:
            if time.time() - begin > timeout_s:
                raise TimeoutException(f"can't transfer leader of {namespace}/{topic}/{partition} to {follower.ip} within {timeout_s} sec")
            try:
                scenario.redpanda_cluster.transfer_leadership_to(follower, namespace, topic, partition)
                break
            except:
                e, v = sys.exc_info()[:2]
                trace = traceback.format_exc()
                logger.error(e)
                logger.error(v)
                logger.error(trace)
                sleep(1)