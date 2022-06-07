from sh import rm
from chaos.checks.result import Result
from chaos.workloads.rw_subscribe.log_utils import State, cmds, threads, phantoms
import logging
import os
from collections import defaultdict

logger = logging.getLogger("consistency")

class LogPlayer:
    def __init__(self):
        self.thread_type = dict()
        self.curr_state = dict()
        self.transitions = defaultdict(lambda: None)
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

        if new_state == State.VIOLATION:
            self.has_violation = True
            logger.error(parts[3])
            return
        if new_state in phantoms:
            return
        
        thread_id = int(parts[0])
        if thread_id not in self.curr_state:
            self.thread_type[thread_id] = parts[4]
            self.curr_state[thread_id] = None
            if self.thread_type[thread_id] not in threads:
                raise Exception(f"unknown thread type: {parts[4]}")
            if new_state != State.STARTED:
                raise Exception(f"first logged command of a new thread should be started, got: \"{parts[2]}\"")
            self.curr_state[thread_id] = new_state
            return
        
        if self.transitions[thread_id] != None:
            if new_state not in self.transitions[thread_id]:
                raise Exception(f"unknown transition {self.curr_state[thread_id]} -> {new_state}\n{line}")
            self.curr_state[thread_id] = new_state
            self.transitions[thread_id] = None
        else:
            sc = threads[self.thread_type[thread_id]][self.curr_state[thread_id]]
            if type(sc) == list:
                if new_state not in sc:
                    raise Exception(f"unknown transition {self.curr_state[thread_id]} -> {new_state}\n{line}")
                self.curr_state[thread_id] = new_state
            elif type(sc) == dict:
                if new_state not in sc:
                    raise Exception(f"unknown transition {self.curr_state[thread_id]} -> {new_state}\n{line}")
                self.curr_state[thread_id] = new_state
                self.transitions[thread_id] = sc[new_state]
            else:
                raise Exception(f"unknown state collection: {type(sc).__name__}")

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
            player = LogPlayer()
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
        logger.exception("error on checking consistency")
        
        return {
            "result": Result.UNKNOWN
        }
    finally:
        handler.flush()
        handler.close()
        logger.removeHandler(handler)

        if not has_errors:
            rm("-rf", logger_handler_path)