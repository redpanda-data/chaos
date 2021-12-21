from enum import Enum
import sys
import json
from sh import mkdir, rm
import traceback
from confluent_kafka import Consumer, TopicPartition, OFFSET_BEGINNING
from chaos.checks.result import Result
from chaos.workloads.tx_subscribe.log_utils import State, cmds, transitions, phantoms
import logging
import os

logger = logging.getLogger("consistency")

class Write:
    def __init__(self):
        self.key = None
        self.op = None
        self.offset = None
        self.started = None
        self.finished = None
        self.max_offset = None

def validate(config, workload_dir):
    logger.setLevel(logging.DEBUG)
    logger_handler_path = os.path.join(workload_dir, "consistency.log")
    handler = logging.FileHandler(logger_handler_path)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(handler)

    has_errors = True
    
    try:
        last_state = dict()
        has_violation = False

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
                    pass
                elif new_state == State.SEND:
                    pass
                elif new_state == State.READ:
                    pass
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

        has_errors = has_violation

        return {
            "result": Result.FAILED if has_violation else Result.PASSED
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