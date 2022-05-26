from enum import Enum
import sys
import json
from sh import mkdir, rm
import traceback
from chaos.checks.result import Result
from chaos.workloads.tx_poll.log_utils import State, cmds, transitions
import logging
import os
from collections import deque

logger = logging.getLogger("consistency")

class LogPlayer:
    def __init__(self, node):
        self.node = node
        
        self.curr_state = dict()
        self.has_violation = False

        self.ts_us = None
    
    def is_violation(self, line):
        if line == None:
            return False
        parts = line.rstrip().split('\t')
        if len(parts)<3:
            return False
        if parts[2] not in cmds:
            return False
        return cmds[parts[2]] == State.VIOLATION
    
    def apply(self, line):
        if self.has_violation:
            return
        parts = line.rstrip().split('\t')

        if parts[2] not in cmds:
            raise Exception(f"unknown cmd \"{parts[2]}\"")

        if self.ts_us == None:
            self.ts_us = int(parts[1])
        else:
            delta_us = int(parts[1])
            self.ts_us = self.ts_us + delta_us
        
        new_state = cmds[parts[2]]

        if new_state == State.EVENT:
            return
        if new_state == State.VIOLATION:
            self.has_violation = True
            logger.error(parts[3])
            return
        if new_state == State.LOG:
            return
        
        thread_id = int(parts[0])
        if thread_id not in self.curr_state:
            self.curr_state[thread_id] = None
        if self.curr_state[thread_id] == None:
            if new_state != State.STARTED:
                raise Exception(f"first logged command of a new thread should be started, got: \"{parts[2]}\"")
            self.curr_state[thread_id] = new_state
        else:
            if new_state not in transitions[self.curr_state[thread_id]]:
                raise Exception(f"unknown transition {self.curr_state[thread_id]} -> {new_state} while processing \"{line.rstrip()}\"")
            self.curr_state[thread_id] = new_state

def validate(config, workload_dir):
    logger.setLevel(logging.DEBUG)
    logger_handler_path = os.path.join(workload_dir, "consistency.log")
    handler = logging.FileHandler(logger_handler_path)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(handler)

    has_errors = True
    
    try:
        has_violation = False
        for node in config["workload"]["nodes"]:
            player = LogPlayer(node)
            with open(os.path.join(workload_dir, node, "workload.log"), "r") as workload_file:
                last_line = None
                for line in workload_file:
                    if last_line != None:
                        player.apply(last_line)
                    last_line = line
                if player.is_violation(last_line):
                    player.apply(last_line)
            has_violation = has_violation or player.has_violation
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