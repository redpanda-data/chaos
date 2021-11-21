from sh import ssh
from sh import cd
from sh import mkdir
from sh import python3
import json
import requests
import os
import sys
import traceback
import time
from time import sleep
from chaos.redpanda_cluster import RedpandaNode, TimeoutException
from chaos.checks.result import Result
from chaos.workloads.writing import consistency
from chaos.workloads.writing import stat

import logging
logger = logging.getLogger("chaos")

class Info:
    def __init__(self):
        self.succeeded_ops = 0
        self.failed_ops = 0
        self.timedout_ops = 0
        self.is_active = 0

class Control:
    def __init__(self):
        self.launch = None
        self.kill = None
        self.alive = None
        self.name = None

class Workload:
    def __init__(self, scripts, nodes_path):
        self.scripts = scripts
        self.nodes = []
        self.name = scripts.name
        with open(nodes_path, "r") as f:
            for line in f:
                line = line.rstrip()
                parts = line.split(" ")
                self.nodes.append(RedpandaNode(parts[0], int(parts[1])))
    
    def is_alive(self, node):
        ip = node.ip
        result = ssh("ubuntu@"+ip, self.scripts.alive)
        return "YES" in result
    
    def launch(self, node):
        ip = node.ip
        ssh("ubuntu@"+ip, self.scripts.launch)
    
    def kill(self, node):
        ip = node.ip
        ssh("ubuntu@"+ip, self.scripts.kill)
    
    def kill_everywhere(self):
        for node in self.nodes:
            logger.debug(f"killing workload process on node {node.ip}")
            self.kill(node)
    
    def stop_everywhere(self):
        for node in self.nodes:
            logger.debug(f"stopping workload on node {node.ip}")
            self.stop(node)
    
    def wait_killed(self, timeout_s=10):
        begin = time.time()
        for node in self.nodes:
            while True:
                if time.time() - begin > timeout_s:
                    raise TimeoutException(f"workload stuck and can't be killed in {timeout_s} sec")
                logger.debug(f"checking if workload process is alive {node.ip}")
                if not self.is_alive(node):
                    break
                sleep(1)
    
    def launch_everywhere(self):
        for node in self.nodes:
            logger.debug(f"starting workload on node {node.ip}")
            self.launch(node)

    def wait_alive(self, timeout_s=10):
        begin = time.time()
        for node in self.nodes:
            while True:
                if time.time() - begin > timeout_s:
                    raise TimeoutException(f"workload process isn't running within {timeout_s} sec")
                logger.debug(f"checking if workload process is running on {node.ip}")
                if self.is_alive(node):
                    break
                sleep(1)
    
    def wait_ready(self, timeout_s=10):
        begin = time.time()
        for node in self.nodes:
            while True:
                if time.time() - begin > timeout_s:
                    raise TimeoutException(f"workload process isn't ready to accept requests within {timeout_s} sec")
                try:
                    logger.debug(f"checking if workload http api is ready on {node.ip}")
                    self.ping(node)
                    break
                except:
                    if not self.is_alive(node):
                        logger.error(f"workload process on {node.ip} (id={node.id}) died")
                        raise
    
    def wait_progress(self, timeout_s=10):
        begin = time.time()
        started = dict()
        for node in self.nodes:
            started[node.ip]=self.info(node)
        made_progress = False
        progressed = dict()
        while True:
            made_progress = True
            for node in self.nodes:
                if time.time() - begin > timeout_s:
                    raise TimeoutException(f"workload haven't done progress within {timeout_s} sec")
                if node.ip in progressed:
                    continue
                logger.debug(f"checking if node {node.ip} made progress")
                info = self.info(node)
                if info.succeeded_ops > started[node.ip].succeeded_ops:
                    progressed[node.id]=True
                else:
                    made_progress = False
            if made_progress:
                break
            sleep(1)

    def emit_event(self, node, name):
        ip = node.ip
        r = requests.post(f"http://{ip}:8080/event/" + name)
        if r.status_code != 200:
            raise Exception(f"unexpected status code: {r.status_code}")

    def init(self, node, server, brokers, topic, experiment, settings):
        ip = node.ip
        r = requests.post(f"http://{ip}:8080/init", json={
            "experiment": experiment,
            "server": server,
            "topic": topic,
            "brokers": brokers,
            "settings": settings})
        if r.status_code != 200:
            raise Exception(f"unexpected status code: {r.status_code}")
    
    def start(self, node):
        ip = node.ip
        r = requests.post(f"http://{ip}:8080/start")
        if r.status_code != 200:
            raise Exception(f"unexpected status code: {r.status_code}")

    def stop(self, node):
        ip = node.ip
        r = requests.post(f"http://{ip}:8080/stop")
        if r.status_code != 200:
            raise Exception(f"unexpected status code: {r.status_code}")

    def info(self, node):
        ip = node.ip
        r = requests.get(f"http://{ip}:8080/info")
        if r.status_code != 200:
            raise Exception(f"unexpected status code: {r.status_code}")
        info = Info()
        info.succeeded_ops = r.json()["succeeded_ops"]
        info.failed_ops = r.json()["failed_ops"]
        info.timedout_ops = r.json()["timedout_ops"]
        info.is_active = r.json()["is_active"]
        return info
    
    def ping(self, node):
        ip = node.ip
        r = requests.get(f"http://{ip}:8080/ping")
        if r.status_code != 200:
            raise Exception(f"unexpected status code: {r.status_code}")

    def analyze(self, config):
        logger.debug(f"analyzing {config['experiment_id']}")

        for check in config["workload"]["checks"]:
            if check["name"] == "consistency":
                check["result"] = Result.PASSED
                for node in self.nodes:
                    workload_dir = f"/mnt/vectorized/experiments/{config['experiment_id']}/{node.ip}"
                    if os.path.isdir(workload_dir):
                        check[node.ip] = consistency.validate(config, workload_dir)
                    else:
                        check[node.ip] = {
                            "result": Result.UNKNOWN,
                            "message": f"Can't find logs dir: {workload_dir}"
                        }
                    check["result"] = Result.more_severe(check["result"], check[node.ip]["result"])
                config["result"] = Result.more_severe(config["result"], check["result"])
            elif check["name"] == "stat":
                check["result"] = Result.PASSED
                for node in self.nodes:
                    workload_dir = f"/mnt/vectorized/experiments/{config['experiment_id']}/{node.ip}"
                    if os.path.isdir(workload_dir):
                        check[node.ip] = stat.collect(config, workload_dir)
                    else:
                        check[node.ip] = {
                            "result": Result.UNKNOWN,
                            "message": f"Can't find logs dir: {workload_dir}"
                        }
                    check["result"] = Result.more_severe(check["result"], check[node.ip]["result"])
                config["result"] = Result.more_severe(config["result"], check["result"])
            else:
                check["result"] = Result.UNKNOWN
                check["message"] = "Unknown check"
                config["result"] = Result.more_severe(config["result"], check["result"])
        
        return config