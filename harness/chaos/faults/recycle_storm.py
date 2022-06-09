from gettext import find
from time import sleep
import time
from sh import ssh
import logging
import json
import random
from chaos.faults.types import FaultType
from chaos.types import TimeoutException
from chaos.faults.fault import OneoffFault

logger = logging.getLogger("chaos")

class NodeTask:
    ADD_NODE = "ADD_NODE"
    REMOVE_NODE = "REMOVE_NODE"

class NetworkTask:
    ONE = "ONE"
    MAJORITY = "MAJORITY"


class RecycleStormFault(OneoffFault):
    def __init__(self, fault_config):
        super().__init__(fault_config)
        self.name = "recycle storm"
        
        self.healing = False

        ## node
        self.free_hosts = set()
        self.active_nodes = set()
        self.version = 0
        
        self.adding_nodes = set()
        self.removing_nodes = set()
        self.decommissioning_nodes = set()

        self.node_ops_executed = 0
        self.node_ops_limit = 20

        ## partition
        self.partitions = dict()
        self.partition_ops_executed = 0
    
    def partition_tick(self, scenario):
        if len(self.partitions) > 0:
            for ip in self.partitions.keys():
                logger.debug(f"reconnecting {ip} to {', '.join(self.partitions[ip])}")
                ssh("ubuntu@"+ip, "/mnt/vectorized/control/network.heal.sh", *self.partitions[ip])
            self.partitions.clear()
            self.partition_ops_executed += 1
            return
        
        if self.healing:
            return

        tasks = []
        tasks.append(NetworkTask.ONE)
        tasks.append(NetworkTask.MAJORITY)
        
        task = random.choice(tasks)
        
        if task == NetworkTask.ONE:
            target = random.choice(scenario.redpanda_cluster.hosts)
            rest = []
            for host in scenario.redpanda_cluster.hosts:
                if target != host:
                    self.partitions[host.ip] = [target.ip]
                    rest.append(host.ip)
            self.partitions[target.ip] = rest
            logger.info(f"isolating {target.ip} from {', '.join(self.partitions[target.ip])}")
        
        if task == NetworkTask.MAJORITY:
            hosts = list(scenario.redpanda_cluster.hosts)
            random.shuffle(hosts)
            pivot = int(len(hosts)/2)
            left = [host.ip for host in hosts[0:pivot]]
            right = [host.ip for host in hosts[pivot:]]
            for node in left:
                self.partitions[node] = right
            for node in right:
                self.partitions[node] = left
            logger.info(f"isolating {', '.join(left)} from {', '.join(right)}")
        
        for ip in self.partitions.keys():
            ssh("ubuntu@"+ip, "/mnt/vectorized/control/network.isolate.sh", *self.partitions[ip])

    def node_tick(self, scenario):
        tasks = []

        if not(self.healing) and len(self.active_nodes)>3:
            tasks.append(NodeTask.REMOVE_NODE)
        if len(self.active_nodes) < 6 and len(self.free_hosts) > 0:
            tasks.append(NodeTask.ADD_NODE)
        
        if len(tasks)>0:
            task = random.choice(tasks)
            if task == NodeTask.REMOVE_NODE:
                candidate = random.choice(list(self.active_nodes))
                self.removing_nodes.add(candidate)
                self.active_nodes.remove(candidate)
                self.decommissioning_nodes.add(candidate)
            
            if task == NodeTask.ADD_NODE:
                candidate = random.choice(list(self.free_hosts))
                self.free_hosts.remove(candidate)
                node_id = scenario.redpanda_cluster.get_id()
                logger.info(f"adding id={node_id} ip={candidate.ip}")
                node = scenario.redpanda_cluster.add_node(candidate, node_id)
                self.adding_nodes.add(node)
                scenario.redpanda_cluster.launch(node)
        
        candidates = list(self.decommissioning_nodes)
        for candidate in candidates:
            logger.info(f"decommissioning id={candidate.id} ip={candidate.ip}")
            try:
                scenario.redpanda_cluster.admin_decommission(candidate, candidate)
                self.decommissioning_nodes.remove(candidate)
            except:
                logger.exception("error with decommissioning, will retry")
        
        candidates = list(self.removing_nodes)
        for candidate in candidates:
            for node in self.active_nodes|self.adding_nodes:
                try:
                    view = scenario.redpanda_cluster.get_view(node)
                except:
                    logger.exception(f"connection problem with {node.ip}")
                    break
                if view["version"] < self.version:
                    continue
                self.version = view["version"]
                if all(broker["node_id"] != candidate.id for broker in view["brokers"]):
                    self.free_hosts.add(candidate.host)
                    self.removing_nodes.remove(candidate)
                    scenario.redpanda_cluster.kill(candidate)
                    scenario.redpanda_cluster.rm_node(candidate)
                    self.node_ops_executed += 1
                    logger.info(f"decommissioned id={candidate.id} ip={candidate.ip}")
                    break
        
        candidates = list(self.adding_nodes)
        for candidate in candidates:
            for node in self.active_nodes|self.adding_nodes:
                try:
                    view = scenario.redpanda_cluster.get_view(node)
                except:
                    logger.exception(f"connection problem with {node.ip}")
                    break
                if view["version"] < self.version:
                    continue
                self.version = view["version"]
                if any(broker["node_id"] == candidate.id for broker in view["brokers"]):
                    self.active_nodes.add(candidate)
                    self.adding_nodes.remove(candidate)
                    self.node_ops_executed += 1
                    logger.info(f"added id={candidate.id} ip={candidate.ip}")
                    break
    
    def execute(self, scenario):
        self.active_nodes = set(scenario.redpanda_cluster.nodes)
        i = 1
        partitioned_s = 5
        healed_s = 5
        while True:
            if self.node_ops_executed >= self.node_ops_limit and self.partition_ops_executed > 5:
                self.healing = True
            if self.healing and len(self.active_nodes)==6 and len(self.partitions)==0:
                break
            self.node_tick(scenario)
            if i%partitioned_s == 0 and len(self.partitions) > 0:
                self.partition_tick(scenario)
                if healed_s < 40:
                    healed_s += 5
            if i%healed_s == 0 and len(self.partitions) == 0:
                self.partition_tick(scenario)
            sleep(1)
            i += 1
