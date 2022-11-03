from enum import Enum
import sys
import json
from sh import mkdir, rm
import traceback
from confluent_kafka import Consumer, TopicPartition, OFFSET_BEGINNING
from chaos.checks.result import Result
from chaos.workloads.tx_compact.log_utils import State, cmds, transitions, phantoms
import logging
import os
from collections import defaultdict
from chaos.workloads.retryable_consumer import RetryableConsumer

logger = logging.getLogger("consistency")

class Write:
    def __init__(self):
        self.seq = -1
        self.ltid= -1

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

        inflight = defaultdict(lambda: [])
        candidates = defaultdict(lambda: dict())
        committed = defaultdict(lambda: dict())
        last_offset = -1

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
                elif new_state == State.ABORT:
                    pass
                elif new_state == State.SEEN:
                    pass
                elif new_state == State.ERROR:
                    pass
                elif new_state == State.EVENT:
                    pass
                elif new_state == State.TX:
                    inflight[thread_id].clear()
                elif new_state == State.LOG:
                    if len(parts) < 4:
                        continue
                    if parts[3] != "put":
                        continue
                    key = parts[4]
                    ltid = int(parts[5])
                    seq = int(parts[6])
                    if parts[7] == "a":
                        continue
                    inflight[thread_id].append([key, ltid, seq])
                elif new_state == State.COMMIT:
                    for [key, ltid, seq] in inflight[thread_id]:
                        candidates[thread_id][key] = [ltid, seq]
                elif new_state == State.OK:
                    if thread_id not in inflight or len(inflight[thread_id])==0:
                        # this is abort
                        continue
                    last_offset = max(last_offset, int(parts[3]))
                    for [key, ltid, seq] in inflight[thread_id]:
                        committed[thread_id][key] = [ltid, seq]
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
            read = dict()
            writes = dict()

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
                        break
                    prev_offset = offset

                    key = msg.key().decode('utf-8')
                    value = msg.value().decode('utf-8')
                    parts = value.split('\t')

                    thread_id = int(parts[0])
                    ltid = int(parts[1])
                    seq = int(parts[2])
                    if parts[3] == "a":
                        logger.error(f"observed aborted tx: {key} {thread_id} {ltid} {seq}")
                        has_violation = True
                        break

                    if thread_id in writes:
                        write = writes[thread_id]
                        if seq <= write.seq:
                            if write.ltid != ltid:
                                has_violation = True
                                logger.error(f"time travel: {key} {thread_id} {ltid} {seq} @ {offset} vs seen {write.ltid}/{write.seq}")
                                break
                        write.seq = seq
                        write.ltid = ltid
                    else:
                        writes[thread_id] = Write()
                        writes[thread_id].seq = seq
                        writes[thread_id].ltid = ltid

                    read[key] = [thread_id, ltid, seq]

                    if offset >= last_offset:
                        is_active = False
                        break
            c.close()
            if not has_violation:
                for key in read.keys():
                    [thread_id, ltid, seq] = read[key]

                    if thread_id not in committed and thread_id not in candidates:
                        has_violation = True
                        logger.error(f"can't find thread {thread_id} in committed nor candidates")
                        break

                    known_key = False
                    known_key = known_key or (thread_id in committed and key in committed[thread_id])
                    known_key = known_key or (thread_id in candidates and key in candidates[thread_id])
                    if not known_key:
                        has_violation = True
                        logger.error(f"can't find key {key} in committed nor candidates")
                        break

                    if thread_id in committed and key in committed[thread_id]:
                        if committed[thread_id][key] == [ltid, seq]:
                            continue

                    if thread_id in candidates and key in candidates[thread_id]:
                        if candidates[thread_id][key] == [ltid, seq]:
                            continue
                    
                    logger.error(f"can't find read {key} {thread_id} {ltid} {seq} in attempted commits")

                    logger.error(f"committed")
                    for thread_id in committed.keys():
                        for key in committed[thread_id].keys():
                            [ltid, seq] = committed[thread_id][key]
                            logger.error(f"\t{key} {thread_id} {ltid} {seq}")
                    
                    logger.error(f"candidates")
                    for thread_id in candidates.keys():
                        for key in candidates[thread_id].keys():
                            [ltid, seq] = candidates[thread_id][key]
                            logger.error(f"\t{key} {thread_id} {ltid} {seq}")

                    has_violation = True
                    break
                pass

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