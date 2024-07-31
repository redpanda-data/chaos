from gettext import find
from socket import timeout
from time import sleep
import time
from sh import ssh
import logging
import json
import random
from chaos.faults.types import FaultType
from chaos.types import TimeoutException
from chaos.faults.fault import OneoffFault
from chaos.scenarios.consts import NODE_ALIVE_AFTER_RESTART_S
from chaos.scenarios.consts import STABLE_VIEW_AFTER_RESTART_S
from chaos.scenarios.consts import CONTROLLER_AVAILABLE_AFTER_RESTART_S

logger = logging.getLogger("chaos")

class RecycleAllFault(OneoffFault):
    def __init__(self, fault_config):
        super().__init__(fault_config)
        self.name = "recycle all"
    
    def add_decommission(self, scenario):
        free_hosts = {
            host for host in scenario.redpanda_cluster.hosts
            if all([node.ip != host.ip for node in scenario.redpanda_cluster.nodes])
        }

        if len(free_hosts) == 0:
            raise Exception("cant find free host")
        
        timeout_s=self.read_config(["timeout_s"], 120)
        controller_timeout_s=self.read_config(["controller_timeout_s"], CONTROLLER_AVAILABLE_AFTER_RESTART_S)

        nodes = list(scenario.redpanda_cluster.nodes)
        random.shuffle(nodes)

        for target in nodes:
            candidate = random.choice(list(free_hosts))
            free_hosts.remove(candidate)
            
            node_id = scenario.redpanda_cluster.get_id()
            logger.info(f"adding id={node_id} ip={candidate.ip}")
            node = scenario.redpanda_cluster.add_node(candidate, node_id)
            log_levels = scenario.log_levels_dict()
            scenario.redpanda_cluster.launch(node, log_levels)
            scenario.redpanda_cluster.wait_alive(node=node, timeout_s=NODE_ALIVE_AFTER_RESTART_S)
            scenario.redpanda_cluster.get_stable_view(timeout_s=STABLE_VIEW_AFTER_RESTART_S)

            controller = scenario.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=controller_timeout_s)
            logger.debug(f"controller id={controller.id} ip={controller.ip}")
            logger.debug(f"decommissioning id={target.id} ip={target.ip}")
            scenario.redpanda_cluster.admin_decommission(target, target)
            begin = time.time()
            while True:
                if time.time() - begin > timeout_s:
                    raise TimeoutException(f"can't see decommission finished")
                removed = False
                for node in scenario.redpanda_cluster.nodes:
                    if node.id == target.id:
                        continue
                    view = None
                    try:
                        view = scenario.redpanda_cluster.get_view(node)
                    except:
                        logger.exception(f"error of getting get_view from {node.ip}")
                        continue
                    removed = all(x['node_id'] != target.id for x in view['brokers'])
                    if removed:
                        break
                if removed:
                    break
                sleep(5)
            scenario.redpanda_cluster.kill(target)
            scenario.redpanda_cluster.rm_node(target)
            logger.debug(f"decommissioned id={target.id} ip={target.ip}")
            free_hosts.add(target.host)

    def decommission_add(self, scenario):
        timeout_s=self.read_config(["timeout_s"], 120)
        controller_timeout_s=self.read_config(["controller_timeout_s"], CONTROLLER_AVAILABLE_AFTER_RESTART_S)

        nodes = list(scenario.redpanda_cluster.nodes)
        random.shuffle(nodes)

        for target in nodes:
            controller = scenario.redpanda_cluster.wait_leader("controller", namespace="redpanda", timeout_s=controller_timeout_s)
            logger.debug(f"controller id={controller.id} ip={controller.ip}")
            logger.debug(f"decommissioning id={target.id} ip={target.ip}")
            scenario.redpanda_cluster.admin_decommission(target, target)
            begin = time.time()
            while True:
                if time.time() - begin > timeout_s:
                    raise TimeoutException(f"can't see decommission finished")
                removed = False
                for node in scenario.redpanda_cluster.nodes:
                    if node.id == target.id:
                        continue
                    view = None
                    try:
                        view = scenario.redpanda_cluster.get_view(node)
                    except:
                        logger.exception(f"error of getting get_view from {node.ip}")
                        continue
                    removed = all(x['node_id'] != target.id for x in view['brokers'])
                    if removed:
                        break
                if removed:
                    break
                sleep(5)
            scenario.redpanda_cluster.kill(target)
            scenario.redpanda_cluster.rm_node(target)
            logger.debug(f"decommissioned id={target.id} ip={target.ip}")
            node_id = scenario.redpanda_cluster.get_id()
            node = scenario.redpanda_cluster.add_node(target.host, node_id)
            logger.info(f"adding id={node.id} ip={node.ip}")
            log_levels = scenario.log_levels_dict()
            log_levels['default'] = scenario.default_log_level()
            scenario.redpanda_cluster.launch(node, log_levels)
            scenario.redpanda_cluster.wait_alive(node=node, timeout_s=NODE_ALIVE_AFTER_RESTART_S)
            scenario.redpanda_cluster.get_stable_view(timeout_s=STABLE_VIEW_AFTER_RESTART_S)
    
    def execute(self, scenario):
        if len(scenario.redpanda_cluster.nodes) == 3:
            self.add_decommission(scenario)
        else:
            self.decommission_add(scenario)