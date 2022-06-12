from enum import Enum
import sys
import json
from sh import mkdir, rm
import traceback
from chaos.workloads.retryable_consumer import RetryableConsumer
from chaos.checks.result import Result
from chaos.workloads.reads_writes.log_utils import State, cmds, transitions, phantoms
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
        key = None
        last_state = dict()
        last_time = None
        last_write = dict()
        max_offset = -1
        has_violation = False

        ok_writes = dict()
        err_writes = dict()

        first_offset = sys.maxsize
        last_offset = 0

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
                    ts_us = None
                    if last_time == None:
                        ts_us = int(parts[1])
                    else:
                        delta_us = int(parts[1])
                        ts_us = last_time + delta_us
                    key = parts[3]
                    last_time = ts_us
                elif new_state == State.CONSTRUCTING:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    last_time = last_time + delta_us
                elif new_state == State.CONSTRUCTED:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    last_time = last_time + delta_us
                elif new_state == State.SENDING:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    last_time = last_time + delta_us
                    write = Write()
                    write.key = key
                    write.op = int(parts[3])
                    write.started = last_time
                    write.max_offset = max_offset
                    last_write[thread_id] = write
                elif new_state == State.OK:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    last_time = last_time + delta_us
                    offset = int(parts[3])
                    first_offset = min(first_offset, offset)
                    last_offset = max(last_offset, offset)
                    write = last_write[thread_id]
                    last_write[thread_id] = None
                    write.offset = offset
                    write.finished = last_time
                    if offset <= write.max_offset:
                        has_violation = True
                        logger.error(f"message got lesser offset that was known ({write.max_offset}) before it's written: {write.key}={write.op}@{offset}")
                    max_offset = max(max_offset, offset)
                    if offset in ok_writes:
                        known = ok_writes[offset]
                        logger.error(f"message got already assigned offset: {write.key}={write.op} vs {known.key}={known.op} @ {offset}")
                        has_violation = True
                    ok_writes[offset] = write
                elif new_state == State.ERROR or new_state == State.TIMEOUT:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    last_time = last_time + delta_us
                    write = last_write[thread_id]
                    last_write[thread_id] = None
                    write.offset = None
                    write.finished = last_time
                    err_writes[write.op] = write
                elif new_state == State.EVENT:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    last_time = last_time + delta_us
                elif new_state == State.DELTA:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    last_time = last_time + delta_us
                elif new_state == State.VIOLATION:
                    parts = line.rstrip().split('\t', 3)
                    msg = parts[3]
                    has_violation = True
                    logger.error(msg)
                else:
                    raise Exception(f"unknown state: {new_state}")

        if not has_violation:
            RETRIES=5
            c = RetryableConsumer(logger, config["brokers"])
            c.init(config["topic"], RETRIES)

            retries=RETRIES

            prev_offset = -1
            is_active = True
            while is_active:
                if retries==0:
                    raise Exception("Can't read from redpanda cluster")
                msgs = c.consume()
                retries-=1
                for msg in msgs:
                    if msg is None:
                        continue
                    if msg.error():
                        logger.debug("Consumer error: {}".format(msg.error()))
                        continue
                    retries=RETRIES

                    offset = msg.offset()

                    if offset <= prev_offset:
                        logger.error(f"offsets must increase; observed {offset} after {prev_offset}")
                        has_violation = True
                    prev_offset = offset

                    if offset<first_offset:
                        continue

                    op = int(msg.value().decode('utf-8'))
                    key = msg.key().decode('utf-8')

                    if offset in ok_writes:
                        write = ok_writes[offset]
                        if write.op != op:
                            logger.error(f"read message {key}={op}@{offset} doesn't match written message {write.key}={write.op}@{offset}")
                            has_violation = True
                        if write.key != key:
                            logger.error(f"read message {key}={op}@{offset} doesn't match written message {write.key}={write.op}@{offset}")
                            has_violation = True
                        del ok_writes[offset]
                        if op in err_writes:
                            raise Exception("wat")
                    elif op in err_writes:
                        write = err_writes[op]
                        if write.key != key:
                            logger.error(f"read message {key}={op}@{offset} doesn't match written message {write.key}={write.op}")
                            has_violation = True
                        if offset <= write.max_offset:
                            logger.error(f"message got lesser offset that was known ({write.max_offset}) before it's written: {write.key}={write.op}@{offset}")
                            has_violation = True
                        del err_writes[op]
                    else:
                        logger.error(f"read unknown message {key}={op}@{offset}")
                        has_violation = True

                    if offset >= last_offset:
                        is_active = False
                        break
            c.close()

            if len(ok_writes) != 0:
                has_violation = True
                for offset in ok_writes:
                    write = ok_writes[offset]
                    logger.error(f"lost message found {write.key}={write.op}@{offset}")

        has_errors = has_violation

        return {
            "result": Result.FAILED if has_violation else Result.PASSED
        }
    except:
        logger.exception("error on analyzing consistency")
        
        return {
            "result": Result.UNKNOWN
        }
    finally:
        handler.flush()
        handler.close()
        logger.removeHandler(handler)

        if not has_errors:
            rm("-rf", logger_handler_path)