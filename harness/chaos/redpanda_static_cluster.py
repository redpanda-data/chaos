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
        self.host = None

class RedpandaHost:
    def __init__(self, ip):
        self.ip = ip

class PartitionDetails:
    def __init__(self):
        self.replicas = []
        self.leader = None
        self.status = None

class RedpandaCluster:
    def __init__(self, nodes_path):
        self.last_id = 0
        self.nodes = []
        self.hosts = []
        self.nodes_path = nodes_path
        with open(nodes_path, "r") as f:
            for line in f:
                line = line.rstrip()
                parts = line.split(" ")
                self.hosts.append(RedpandaHost(parts[0]))
    
    def get_id(self):
        self.last_id += 1
        return self.last_id
    
    def add_seed(self, host, node_id):
        for node in self.nodes:
            if node.ip == host.ip:
                raise Exception(f"node with ip={host.ip} is already added")
            if node.id == node_id:
                raise Exception(f"node with id={node_id} is already added")
        node = RedpandaNode(host.ip, node_id)
        node.host = host
        self.nodes.append(node)
        logger.info(f"adding seed id={node_id} ip={host.ip}")
        ssh("ubuntu@" + host.ip, "/mnt/vectorized/control/redpanda.identity.sh", node_id, host.ip)
        return node
    
    def add_node(self, host, node_id):
        rest = []
        for node in self.nodes:
            if node.ip == host.ip:
                raise Exception(f"node with ip={host.ip} is already added")
            if node.id == node_id:
                raise Exception(f"node with id={node_id} is already added")
            rest.append(node.ip)
        node = RedpandaNode(host.ip, node_id)
        node.host = host
        self.nodes.append(node)
        logger.info(f"adding node id={node_id} ip={host.ip}")
        ssh("ubuntu@" + host.ip, "/mnt/vectorized/control/redpanda.identity.sh", node_id, host.ip, ",".join(rest))
        return node
    
    def rm_node(self, node):
        logger.info(f"removing node id={node.id} ip={node.ip}")
        self.nodes = list(filter(lambda x: x.id!=node.id, self.nodes))
        ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/redpanda.clean.data.sh")
    
    def get_view(self, node):
        r = requests.get(f"http://{node.ip}:9644/v1/cluster_view")
        if r.status_code != 200:
            raise HTTPErrorException(r)
        
        view = r.json()

        reduced = dict()
        reduced["version"] = view["version"]
        reduced["brokers"] = list(map(
            lambda x: {
                "node_id": x["node_id"],
                "membership_status": x["membership_status"],
                "is_alive": x["is_alive"]
            },
            view["brokers"]))
        logger.debug(f"cluster view from: {node.ip}: {json.dumps(reduced)}")
        return r.json()
    
    def get_stable_view(self, nodes=None, timeout_s=10):
        if nodes == None:
            nodes = self.nodes
        begin = time.time()
        while True:
            random.shuffle(nodes)
            msg = ",".join(map(lambda node: f"{node.id}", nodes))
            logger.info(f"wait stable view from nodes: {msg}")
            if time.time() - begin > timeout_s:
                raise TimeoutException(f"can't fetch stable view {timeout_s} sec")
            common_view = None
            for node in nodes:
                node_view = None
                try:
                    node_view = self.get_view(node)
                except:
                    common_view = None
                    logger.exception("error on getting view from {node.ip}")
                    break
                if node == nodes[0]:
                    common_view = node_view
                if common_view["version"] != node_view["version"]:
                    logger.debug(f"get version:{node_view['version']} while already observed:{common_view['version']} before")
                    common_view = None
                    break
            if common_view != None:
                return common_view
            sleep(1)
    
    def heal(self):
        for node in self.nodes:
            ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/network.heal.all.sh")

    def launch(self, node, log_levels = None):
        if log_levels == None:
            log_levels = {}
        log_levels = log_levels.copy()
        if "default" not in log_levels:
            log_levels["default"] = "info"
        default = log_levels["default"]
        del log_levels["default"]
        if len(log_levels) == 0:
            log_levels["tx"] = default
        levels_arg = ":".join([f"{k}={v}" for k, v in log_levels.items()])
        ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/redpanda.start.sh", default, levels_arg)
    
    def is_alive(self, node):
        result = ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/redpanda.alive.sh")
        return "YES" in result
    
    def kill(self, node):
        ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/redpanda.stop.sh")

    def clean(self, node):
        ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/redpanda.clean.sh")
    
    def kill_everywhere(self):
        for node in self.hosts:
            logger.debug(f"stopping a redpanda instance on {node.ip}")
            self.kill(node)
    
    def wait_killed(self, timeout_s=10):
        begin = time.time()
        for node in self.hosts:
            while True:
                if time.time() - begin > timeout_s:
                    raise TimeoutException(f"redpanda stuck and can't be stopped in {timeout_s} sec")
                logger.debug(f"checking if redpanda process is running on {node.ip}")
                if not self.is_alive(node):
                    break
                sleep(1)
    
    def clean_everywhere(self):
        for node in self.hosts:
            logger.debug(f"cleaning a redpanda instance on {node.ip}")
            self.clean(node)
    
    def launch_everywhere(self, settings, log_levels=None):
        for node in self.nodes:
            logger.info(f"starting a redpanda instance on {node.ip} with {json.dumps(settings)}")
            for key in settings.keys():
                ssh("ubuntu@" + node.ip, "/mnt/vectorized/control/redpanda.config.sh", key, settings[key])
            self.launch(node, log_levels)

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
        return ",".join([x.ip+":9092" for x in self.hosts])
    
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