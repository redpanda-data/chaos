import time
import json
import requests
from time import sleep
from sh import ssh
import sys
import traceback
import random
from chaos.types import TimeoutException

import logging
logger = logging.getLogger("chaos")

class HTTPErrorException(Exception):
    def __init__(self, response):
        self.response = response
    
    def __str__(self) -> str:
        return f"error code: {self.response.status_code} content: {self.response.content}"

class RedpandaNode:
    def __init__(self, ip, id):
        self.ip = ip
        self.id = id

class PartitionDetails:
    def __init__(self):
        self.replicas = []
        self.leader = None
        self.status = None

class RedpandaCluster:
    def __init__(self, nodes_path):
        self.nodes = []
        with open(nodes_path, "r") as f:
            for line in f:
                line = line.rstrip()
                parts = line.split(" ")
                self.nodes.append(RedpandaNode(parts[0], int(parts[1])))
        logger.debug(f"RedpandaCluster inited with:")
        for node in self.nodes:
            logger.debug(f"node id={node.id} ip={node.ip}")
    
    def heal(self):
        for node in self.nodes:
            ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/network.heal.all.sh")

    def launch(self, node):
        ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/redpanda.start.sh")
    
    def is_alive(self, node):
        result = ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/redpanda.alive.sh")
        return "YES" in result
    
    def kill(self, node):
        ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/redpanda.stop.sh")

    def clean(self, node):
        ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/redpanda.clean.sh")
    
    def kill_everywhere(self):
        for node in self.nodes:
            logger.debug(f"stopping a redpanda instance on {node.ip}")
            self.kill(node)
    
    def wait_killed(self, timeout_s=10):
        begin = time.time()
        for node in self.nodes:
            while True:
                if time.time() - begin > timeout_s:
                    raise TimeoutException(f"redpanda stuck and can't be stopped in {timeout_s} sec")
                logger.debug(f"checking if redpanda process is running on {node.ip}")
                if not self.is_alive(node):
                    break
                sleep(1)
    
    def clean_everywhere(self):
        for node in self.nodes:
            logger.debug(f"cleaning a redpanda instance on {node.ip}")
            self.clean(node)
    
    def launch_everywhere(self, settings):
        for node in self.nodes:
            logger.debug(f"starting a redpanda instance on {node.ip} with {json.dumps(settings)}")
            for key in settings.keys():
                ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/redpanda.config.sh", key, settings[key])
            self.launch(node)

    def wait_alive(self, timeout_s=10):
        begin = time.time()
        for node in self.nodes:
            while True:
                if time.time() - begin > timeout_s:
                    raise TimeoutException(f"redpanda process isn't running withing {timeout_s} sec")
                logger.debug(f"checking if redpanda is running on {node.ip}")
                if self.is_alive(node):
                    break
                sleep(1)
    
    def brokers(self):
        return ",".join(map(lambda x: x.ip+":9092", self.nodes))
    
    def create_topic(self, topic, replication, partitions, cleanup="delete"):
        ssh("ubuntu@" + self.nodes[0].ip, "rpk", "topic", "create", "--brokers", self.brokers(), topic, "-r", replication, "-p", partitions, "-c", f"cleanup.policy={cleanup}")
    
    def reconfigure(self, leader, replicas, topic, partition=0, namespace="kafka"):
        payload = []
        for replica in replicas:
            payload.append({
                "node_id": replica.id,
                "core": 0
            })
        r = requests.post(f"http://{leader.ip}:9644/v1/partitions/{namespace}/{topic}/{partition}/replicas", json=payload)
        if r.status_code != 200:
            logger.error(f"Can't reconfigure, status:{r.status_code} body:{r.text}")
            raise Exception(f"Can't reconfigure, status:{r.status_code} body:{r.text}")

    def _get_stable_details(self, nodes, topic, partition=0, namespace="kafka", replication=None):
        last_leader = -1
        replicas = None
        status = None
        for node in nodes:
            ip = node.ip
            logger.debug(f"requesting \"{namespace}/{topic}/{partition}\" details from {node.id} ({node.ip})")
            meta = self._get_details(node, namespace, topic, partition)
            if meta == None:
                return None
            if "replicas" not in meta:
                logger.debug(f"replicas are missing")
                return None
            if "status" not in meta:
                logger.debug(f"status is missing")
                return None
            if status == None:
                status = meta["status"]
                logger.debug(f"get status:{status}")
            if status != meta["status"]:
                logger.debug(f"get status:{meta['status']} while already observed:{status} before")
                return None
            if replicas == None:
                replicas = {}
                for replica in meta["replicas"]:
                    replicas[replica["node_id"]] = True
                logger.debug(f"get replicas:{','.join(map(str, replicas.keys()))}")
            else:
                read_replicas = {}
                for replica in meta["replicas"]:
                    read_replicas[replica["node_id"]] = True
                if len(replicas) != len(read_replicas):
                    logger.debug(f"get conflicting replicas:{','.join(map(str, read_replicas.keys()))}")
                    return None
                for replica in meta["replicas"]:
                    if replica["node_id"] not in replicas:
                        logger.debug(f"get conflicting replicas:{','.join(map(str, read_replicas.keys()))}")
                        return None
            if replication != None:
                if len(meta["replicas"]) != replication:
                    logger.debug(f"expected replication:{replication} got:{len(meta['replicas'])}")
                    return None
            if meta["leader_id"] < 0:
                logger.debug(f"doesn't have leader")
                return None
            if last_leader < 0:
                last_leader = meta["leader_id"]
                logger.debug(f"get leader:{last_leader}")
            if last_leader not in replicas:
                logger.debug(f"leader:{last_leader} isn't in the replica set")
                return None
            if last_leader != meta["leader_id"]:
                logger.debug(f"got leader:{meta['leader_id']} but observed {last_leader} before")
                return None
        info = PartitionDetails()
        info.status = status
        for node in self.nodes:
            if node.id==last_leader:
                info.leader = node
            if node.id in replicas:
                info.replicas.append(node)
                del replicas[node.id]
        if len(replicas) != 0:
            raise Exception(f"Can't find replicas {','.join(replicas.keys())} in the cluster")
        return info
    
    def wait_details(self, topic, partition=0, namespace="kafka", replication=None, timeout_s=10, nodes=None):
        if nodes == None:
            nodes = self.nodes
        nodes = list(nodes)
        begin = time.time()
        info = None
        while info == None:
            random.shuffle(nodes)
            msg = ",".join(map(lambda node: f"{node.id}", nodes))
            logger.debug(f"wait details for {namespace}/{topic}/{partition} from nodes: {msg}")
            if time.time() - begin > timeout_s:
                raise TimeoutException(f"can't fetch stable replicas for {namespace}/{topic}/{partition} within {timeout_s} sec")
            try:
                info = self._get_stable_details(nodes, topic, partition=partition, namespace=namespace, replication=replication)
                if info == None:
                    sleep(1)
            except:
                e, v = sys.exc_info()[:2]
                trace = traceback.format_exc()
                logger.error(e)
                logger.error(v)
                logger.error(trace)
                sleep(1)
        return info
    
    def wait_leader(self, topic, partition=0, namespace="kafka", replication=None, timeout_s=10):
        info = self.wait_details(topic, partition=partition, namespace=namespace, replication=replication, timeout_s=timeout_s)
        return info.leader
    
    def wait_leader_is(self, target, namespace, topic, partition, timeout_s=10):
        begin = time.time()
        while True:
            if time.time() - begin > timeout_s:
                raise TimeoutException(f"{target.ip} (id={target.id}) hasn't became leader for {namespace}/{topic}/{partition} within {timeout_s} sec")
            leader = self.wait_leader(topic, partition, namespace, timeout_s=timeout_s)
            if leader == target:
                return
            sleep(1)
    
    def _get_details(self, node, namespace, topic, partition):
        ip = node.ip
        r = requests.get(f"http://{ip}:9644/v1/partitions/{namespace}/{topic}/{partition}")
        if r.status_code != 200:
            logger.error(f"status code: {r.status_code}")
            logger.error(f"content: {r.content}")
            return None
        return r.json()
    
    def any_node_but(self, that):
        for node in self.nodes:
            if node != that:
                return node
        raise Exception(f"can't find any but ip: {that.ip}")
    
    def transfer_leadership_to(self, target, namespace, topic, partition):
        logger.debug(f"transfering leadership of \"{namespace}/{topic}/{partition}\" to {target.ip} ({target.id})")
        node = self.wait_leader(topic, partition, namespace)

        logger.debug(f"current leader: {node.ip} (id={node.id})")
        if node.id == target.id:
            logger.debug(f"leader is already there")
            return
        meta = self._get_details(node, namespace, topic, partition)
        if meta == None:
            raise Exception("expected details got none")

        raft_group_id = meta["raft_group_id"]
        r = requests.post(f"http://{node.ip}:9644/v1/raft/{raft_group_id}/transfer_leadership?target={target.id}")
        if r.status_code != 200:
            logger.error(f"status code: {r.status_code}")
            logger.error(f"content: {r.content}")
            raise Exception(f"Can't transfer to id={target.id}")
    
    def admin_decommission(self, node, to_decommission_node):
        r = requests.put(f"http://{node.ip}:9644/v1/brokers/{to_decommission_node.id}/decommission")
        if r.status_code != 200:
            raise HTTPErrorException(r)
    
    def admin_brokers(self, node):
        r = requests.get(f"http://{node.ip}:9644/v1/brokers")
        if r.status_code != 200:
            return None
        return r.json()