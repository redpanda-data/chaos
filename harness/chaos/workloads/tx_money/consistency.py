from enum import Enum
import sys
import json
from sh import mkdir, rm
import traceback
from confluent_kafka import KafkaException, Producer
from chaos.workloads.retryable_consumer import RetryableConsumer
from chaos.checks.result import Result
from chaos.workloads.tx_money.log_utils import State, cmds, transitions, phantoms
from chaos.scenarios.abstract_single_fault import read_config
import logging
import os
from time import sleep

logger = logging.getLogger("consistency")

class Write:
    def __init__(self):
        self.key = None
        self.op = None
        self.offset = None
        self.started = None
        self.finished = None
        self.max_offset = None

class SyncTxProducer:
    def __init__(self, brokers, retries, tx_id):
        self.brokers = brokers
        self.retries = retries
        self.tx_id = tx_id
        self.producer = None
        self.last_msg = None
    
    def init(self):
        self.producer = Producer({
            "bootstrap.servers": self.brokers,
            "topic.metadata.refresh.interval.ms": 5000,
            "metadata.max.age.ms": 10000,
            "topic.metadata.refresh.fast.interval.ms": 250,
            "topic.metadata.propagation.max.ms": 10000,
            "socket.timeout.ms": 10000,
            "connections.max.idle.ms": 0,
            "reconnect.backoff.ms": 100,
            "reconnect.backoff.max.ms": 10000,
            "statistics.interval.ms": 0,
            "api.version.request.timeout.ms": 10000,
            "api.version.fallback.ms": 0,
            "queue.buffering.max.ms": 0,
            "retry.backoff.ms": 100,
            "sticky.partitioning.linger.ms": 10,
            "message.timeout.ms": 10000,
            "request.required.acks": -1,
            "retries": self.retries,
            "enable.idempotence": True,
            "transactional.id": self.tx_id
        })
        self.producer.init_transactions()

    
    def on_delivery(self, err, msg):
        if err is not None:
            raise KafkaException(err)
        self.last_msg = msg
    
    def produce(self, topic, key, value):
        self.last_msg = None
        self.producer.begin_transaction()
        self.producer.produce(
            topic,
            key=key,
            value=value,
            callback=lambda e, m: self.on_delivery(e,m))
        self.producer.commit_transaction()
        msg = self.last_msg
        self.last_msg = None
        if msg.error() != None:
            raise KafkaException(msg.error())
        if msg.offset() == None:
            raise Exception("offset() of a successful produce can't be None")
        return {
            "offset": msg.offset()
        }

def validate(config, workload_dir):
    logger.setLevel(logging.DEBUG)
    logger_handler_path = os.path.join(workload_dir, "consistency.log")
    handler = logging.FileHandler(logger_handler_path)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(handler)

    fail_on_interruption = read_config(config, ["settings", "fail_on_interruption"], False)

    has_errors = True
    
    try:
        last_state = dict()
        has_violation = False

        errors = 0

        with open(os.path.join(workload_dir, "workload.log"), "r") as workload_file:
            for line in workload_file:
                parts = line.rstrip().split('\t')

                thread_id = int(parts[0])
                if thread_id not in last_state:
                    last_state[thread_id] = State.INIT

                if parts[2] not in cmds:
                    raise Exception(f"unknown cmd \"{parts[2]}\"")
                new_state = cmds[parts[2]]

                if new_state not in phantoms:
                    if new_state not in transitions[last_state[thread_id]]:
                        raise Exception(f"unknown transition {last_state[thread_id]} -> {new_state}")
                    last_state[thread_id] = new_state

                if new_state == State.STARTED:
                    pass
                elif new_state == State.CONSTRUCTING:
                    pass
                elif new_state == State.CONSTRUCTED:
                    pass
                elif new_state == State.TX:
                    pass
                elif new_state == State.COMMIT or new_state == State.ABORT:
                    pass
                elif new_state == State.OK:
                    pass
                elif new_state == State.ERROR:
                    errors+=1
                elif new_state == State.EVENT:
                    pass
                elif new_state == State.LOG:
                    pass
                elif new_state == State.VIOLATION:
                    parts = line.rstrip().split('\t', 3)
                    msg = parts[3]
                    has_violation = True
                    logger.error(msg)
                else:
                    raise Exception(f"unknown state: {new_state}")
        
        if fail_on_interruption:
            if errors>0:
                logger.error(f"a client had {errors} interruptions")
                has_violation = True

        if not has_violation:
            sync_producer = None

            total = 0
            # making sure all ongoing transactions has finished
            sync_producer = None
            for i in range(0, config["workload"]["settings"]["producers"]):
                attempt = 0
                while True:
                    logger.debug(f"hijacking tx-{i} tx.id")
                    try:
                        sync_producer = SyncTxProducer(config["brokers"], config["workload"]["settings"]["retries"], f"tx-{i}")
                        sync_producer.init()
                        break
                    except KafkaException as e:
                        if attempt > 6:
                            raise e
                    attempt += 1
                    if attempt % 2 == 0:
                        sleep(1)
            
            RETRIES=5
            for i in range(0, config["accounts"]):
                last_offset = sync_producer.produce(f"acc{i}", None, "0".encode('utf-8'))["offset"]
                c = RetryableConsumer(logger, config["brokers"])
                c.init(f"acc{i}", RETRIES)
                retries=RETRIES

                is_active = True
                while is_active:
                    if retries==0:
                        raise Exception("Can't connect to the redpanda cluster")
                    msgs = c.consume(timeout=10)
                    retries-=1
                    for msg in msgs:
                        if msg is None:
                            continue
                        if msg.error():
                            logger.debug("Consumer error: {}".format(msg.error()))
                            continue
                        retries=RETRIES

                        offset = msg.offset()
                        value = int(msg.value().decode('utf-8'))
                        total += value

                        if offset >= last_offset:
                            is_active = False
                            break
                c.close()
                logger.debug(f"total: {total}")
            if total != 0:
                has_violation = True
            has_errors = has_violation
            return {
                "result": Result.FAILED if has_violation else Result.PASSED,
                "total": total
            }
        has_errors = True
        return {
            "result": Result.FAILED
        }
    except:
        e, v = sys.exc_info()[:2]
        trace = traceback.format_exc()
        logger.debug(v)
        logger.debug(trace)
        
        return {
            "result": Result.UNKNOWN
        }
    finally:
        handler.flush()
        handler.close()
        logger.removeHandler(handler)

        if not has_errors:
            rm("-rf", logger_handler_path)