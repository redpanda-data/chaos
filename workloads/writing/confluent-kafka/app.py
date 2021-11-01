from confluent_kafka import (Producer, KafkaException, KafkaError)
import sys
import traceback
import time
from time import sleep
from sh import mkdir
import os
import threading
from flask import Flask, request
from threading import Lock
from enum import Enum

class SyncClient:
    def __init__(self, bootstrap):
        self.bootstrap = bootstrap
        self.producer = None
        self.last_msg = None
    
    def init(self):
        self.producer = Producer({
            "bootstrap.servers": self.bootstrap,
            "topic.metadata.refresh.interval.ms": 5000, # default: 300000
            "metadata.max.age.ms": 10000, # default: 900000
            "topic.metadata.refresh.fast.interval.ms": 250, # default: 250
            "topic.metadata.propagation.max.ms": 10000, # default: 30000
            "socket.timeout.ms": 10000, # default: 60000
            "connections.max.idle.ms": 0, # default: 0
            "reconnect.backoff.ms": 100, # default: 100
            "reconnect.backoff.max.ms": 10000, # default: 10000
            "statistics.interval.ms": 0, # default: 0
            "api.version.request.timeout.ms": 10000, # default: 10000
            "api.version.fallback.ms": 0, # default: 0
            "queue.buffering.max.ms": 0, # default: 5
            "retry.backoff.ms": 100, # default: 100
            "sticky.partitioning.linger.ms": 10, # default: 10
            "message.timeout.ms": 10000, # default: 300000
            "request.required.acks": -1,
            "retries": 0,
            "enable.idempotence": False
            })
    
    def on_delivery(self, err, msg):
        if err is not None:
            raise KafkaException(err)
        self.last_msg = msg
    
    def produce(self, topic, key, value):
        self.last_msg = None
        self.producer.produce(
            topic,
            key=key,
            value=value,
            callback=lambda e, m: self.on_delivery(e,m))
        self.producer.flush()
        msg = self.last_msg
        self.last_msg = None
        if msg.error() != None:
            raise KafkaException(msg.error())
        if msg.offset() == None:
            raise Exception("offset() of a successful produce can't be None")
        return {
            "offset": msg.offset()
        }

class Params:
    def __init__(self, cfg):
        self.experiment = cfg["experiment"]
        self.server = cfg["server"]
        self.brokers = cfg["brokers"]
        self.topic = cfg["topic"]

class Workload:
    def __init__(self, args):
        self.args = args
        self.succeeded_ops = 0
        self.failed_ops = 0
        self.timedout_ops = 0
        self.is_active = False
        self.threads = []
        self.mutex = Lock()
        self.opslog = None
        self.past_us = 0
    
    def start(self):
        mkdir("-p", os.path.join(self.args.experiment, self.args.server))
        
        self.is_active = True
        self.opslog = open(os.path.join(self.args.experiment, self.args.server, "workload.log"), "w")
        thread = threading.Thread(target=lambda: self.process(0))
        thread.start()
        self.threads.append(thread)
    
    def stop(self):
        self.is_active = False
        for thread in self.threads:
            thread.join()
        self.opslog.close()
    
    def log(self, thread_id, message):
        self.mutex.acquire()
        now_us = int(time.time()*1000000)
        if now_us < self.past_us:
            raise Exception(f"Time cant go back, observed: {now_us} after: {before_us}")
        self.opslog.write(f"{thread_id}\t{now_us - self.past_us}\t{message}\n")
        self.past_us = now_us
        self.mutex.release()
    
    def event(self, name):
        self.log(-1, "event\t" + name)
    
    def process(self, thread_id):
        client = SyncClient(self.args.brokers)
        tick = time.time()
        started = tick
        count = 0
        op = 0

        self.log(thread_id, f"started\t{self.args.server}")

        while self.is_active:
            op+=1

            try:
                if client.producer == None:
                    self.log(thread_id, "constructing")
                    client.init()
                    self.log(thread_id, "constructed");
                    self.succeeded_ops += 1
                    continue
            except:
                self.log(thread_id, "err")
                self.failed_ops += 1
                e, v = sys.exc_info()[:2]
                trace = traceback.format_exc()
                print(v)
                print(trace)
                continue

            try:
                self.log(thread_id, f"msg\t{op}")
                result = client.produce(self.args.topic, self.args.server.encode('utf-8'), str(op).encode('utf-8'))
                offset = result["offset"]
                self.log(thread_id, f"ok\t{offset}")
                self.succeeded_ops += 1
                count += 1
                now = time.time()
                if now - tick > 1:
                    print(f"{int(now-started)}\t{count}")
                    tick = now
                    count = 0
            except KafkaException as err:
                code = err.args[0].code()
                if code == KafkaError._MSG_TIMED_OUT:
                    self.log(thread_id, "time")
                    self.timedout_ops += 1
                    print("timeout")
                else:
                    self.log(thread_id, "err")
                    self.failed_ops += 1
                    print(f"KafkaError with code: {code}")
            except:
                self.log(thread_id, "err")
                self.failed_ops += 1
                e, v = sys.exc_info()[:2]
                trace = traceback.format_exc()
                print(v)
                print(trace)

class State(Enum):
    FRESH = 0
    INITIALIZED = 1
    STARTED = 2
    STOPPED = 3

class AppState:
    def __init__(self):
        self.state = State.FRESH
        self.args = None
        self.workload = None
    
    def init(self, args):
        if self.state != State.FRESH:
            raise Exception(f"Unexpected state: {self.state}")
        mkdir(args.experiment)
        self.state = State.INITIALIZED
        self.args = args

    def start(self):
        if self.state != State.INITIALIZED:
            raise Exception(f"Unexpected state: {self.state}")
        self.state = State.STARTED
        self.workload = Workload(self.args)
        self.workload.start()
    
    def stop(self):
        if self.state != State.STARTED:
            raise Exception(f"Unexpected state: {self.state}")
        self.workload.stop()
        self.state = State.STOPPED
    
    def info(self):
        result = {
            "succeeded_ops": 0,
            "failed_ops": 0,
            "timedout_ops": 0,
            "is_active": False
        }
        if self.workload != None:
            result["succeeded_ops"] = self.workload.succeeded_ops
            result["failed_ops"] = self.workload.failed_ops
            result["timedout_ops"] = self.workload.timedout_ops
            result["is_active"] = self.workload.is_active
        return result
    
    def event(self, name):
        if self.state != State.STARTED:
            raise Exception(f"Unexpected state: {self.state}")
        self.workload.event(name)


state = AppState()
app = Flask(__name__)

@app.route('/init', methods=['POST'])
def init():
    # curl -X POST http://127.0.0.1:8080/init -H 'Content-Type: application/json' -d '{"topic":"topic1","brokers":"127.0.0.1:9092","experiment":"experiment1", "server":"server1"}'
    body = request.get_json(force=True)
    args = Params(body)
    state.init(args)
    return ""

@app.route('/ping', methods=['GET'])
def ping():
    # curl http://127.0.0.1:8080/ping
    return ""

@app.route('/start', methods=['POST'])
def start():
    # curl -X POST http://127.0.0.1:8080/start
    state.start()
    return ""

@app.route('/stop', methods=['POST'])
def stop():
    # curl -X POST http://127.0.0.1:8080/stop
    state.stop()
    return ""

@app.route('/info', methods=['GET'])
def info():
    # curl http://127.0.0.1:8080/info
    return state.info()

@app.route('/event/<name>', methods=['POST'])
def event(name):
    state.event(name)
    return ""

app.run(host='0.0.0.0', port=8080, use_reloader=False, threaded=True)