from sh import gnuplot, rm, cd
import jinja2
import sys
import traceback
import json
import os
from chaos.checks.result import Result
from chaos.workloads.tx_poll.log_utils import State, cmds, transitions
import logging

logger = logging.getLogger("stat")

OVERVIEW = """
set terminal png size 1600,1200
set output "overview.png"
set multiplot
set lmargin 10
set rmargin 10
set tmargin 3

set pointsize 0.2
set xrange [0:{{ duration }}]

set yrange [0:{{ consume_big_latency }}]
set size 1, 0.3
set origin 0, 0
set title "consume"
show title
set parametric
{% for fault in faults %}plot [t=0:{{ consume_big_latency }}] {{ fault }}/1000,t notitle lt rgb "red"
{% endfor %}{% for recovery in recoveries %}plot [t=0:{{ consume_big_latency }}] {{ recovery }}/1000,t notitle lt rgb "blue"
{% endfor %}unset parametric
plot 'latency_consume_ok.log' using ($1/1000):2 title "latency consume (us)" with points lt rgb "black" pt 7,\\
     'latency_consume_err.log' using ($1/1000):2 title "latency err (us)" with points lt rgb "red" pt 7,\\
     {{consume_p99}} title "p99" with lines lt 1
set notitle

set y2range [0:{{ produce_big_latency }}]
set yrange [0:{{ produce_big_latency }}]
set size 1, 0.3
set origin 0, 0.3
set title "produce"
show title
unset ytics
set y2tics auto
set parametric
{% for fault in faults %}plot [t=0:{{ produce_big_latency }}] {{ fault }}/1000,t notitle lt rgb "red"
{% endfor %}{% for recovery in recoveries %}plot [t=0:{{ produce_big_latency }}] {{ recovery }}/1000,t notitle lt rgb "blue"
{% endfor %}unset parametric
plot 'latency_produce_ok.log' using ($1/1000):2 title "latency produce (us)" with points lt rgb "black" pt 7,\\
     'latency_produce_err.log' using ($1/1000):2 title "latency err (us)" with points lt rgb "red" pt 7,\\
     {{produce_p99}} title "p99" with lines lt 1
set notitle

set title "{{ title }}"
show title

set yrange [0:{{ throughput }}]

set size 1, 0.4
set origin 0, 0.6
set format x ""
set bmargin 0
unset y2tics
set ytics

set parametric
{% for fault in faults %}plot [t=0:{{ throughput }}] {{ fault }}/1000,t notitle lt rgb "red"
{% endfor %}{% for recovery in recoveries %}plot [t=0:{{ throughput }}] {{ recovery }}/1000,t notitle lt rgb "blue"
{% endfor %}unset parametric

plot 'throughput.log' using ($1/1000):2 title "throughput - all (per 1s)" with line lt rgb "black"
     

unset multiplot
"""

class Throughput:
    def __init__(self):
        self.count = 0
        self.time_ms = 0
        self.history = []
    
    def tick(self, now_ms):
        while self.time_ms + 1000 < now_ms:
            ts = int(self.time_ms+1000)
            self.history.append([ts, self.count])
            self.count = 0
            self.time_ms += 1000

class ThroughputBuilder:
    def __init__(self):
        self.total_throughput = None
    
    def build(self, config, latencies):
        self.total_throughput = Throughput()
        
        for [ts_ms, latency_us] in latencies:
            self.total_throughput.tick(ts_ms)
            self.total_throughput.count += 1

class LogPlayer:
    def __init__(self, config):
        self.config = config
        
        self.curr_state = dict()

        self.started_us = None
        
        self.ts_us = None

        self.latency_produce_ok_history = []
        self.latency_consume_ok_history = []
        self.latency_produce_err_history = []
        self.latency_consume_err_history = []
        self.faults = []
        self.recoveries = []

        self.txn_started = dict()

        self.should_measure = False
    
    def process_apply(self, thread_id, parts):
        if self.curr_state[thread_id] in [State.PRODUCE, State.CONSUME]:
            self.txn_started[thread_id] = self.ts_us
        elif self.curr_state[thread_id] in [State.ABORT_PRODUCE, State.ERR_PRODUCE, State.ABORT_CONSUME, State.ERR_CONSUME]:
            if self.should_measure:
                if self.curr_state[thread_id] in [State.ABORT_PRODUCE, State.ERR_PRODUCE]:
                    self.latency_produce_err_history.append([int((self.ts_us-self.started_us)/1000), self.ts_us-self.txn_started[thread_id]])
                if self.curr_state[thread_id] in [State.ABORT_CONSUME, State.ERR_CONSUME]:
                    self.latency_consume_err_history.append([int((self.ts_us-self.started_us)/1000), self.ts_us-self.txn_started[thread_id]])
            del self.txn_started[thread_id]
        elif self.curr_state[thread_id] in [State.COMMIT_PRODUCE, State.COMMIT_CONSUME]:
            if self.should_measure:
                if self.curr_state[thread_id] == State.COMMIT_PRODUCE:
                    self.latency_produce_ok_history.append([int((self.ts_us-self.started_us)/1000), self.ts_us-self.txn_started[thread_id]])
                if self.curr_state[thread_id] == State.COMMIT_CONSUME:
                    self.latency_consume_ok_history.append([int((self.ts_us-self.started_us)/1000), self.ts_us-self.txn_started[thread_id]])
            del self.txn_started[thread_id]
    
    def apply(self, line):
        parts = line.rstrip().split('\t')

        if parts[2] not in cmds:
            raise Exception(f"unknown cmd \"{parts[2]}\"")

        if self.ts_us == None:
            self.ts_us = int(parts[1])
            self.started_us = self.ts_us
        else:
            delta_us = int(parts[1])
            self.ts_us = self.ts_us + delta_us
        
        new_state = cmds[parts[2]]

        if new_state == State.EVENT:
            name = parts[3]
            if name == "measure" and not self.should_measure:
                self.started_us = self.ts_us
                self.should_measure = True
            if self.should_measure:
                if name=="injecting" or name=="injected":
                    self.faults.append(int((self.ts_us - self.started_us)/1000))
                elif name=="healing" or name=="healed":
                    self.recoveries.append(int((self.ts_us - self.started_us)/1000))
            return
        if new_state == State.VIOLATION:
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
                raise Exception(f"unknown transition {self.curr_state[thread_id]} -> {new_state}")
            self.curr_state[thread_id] = new_state
        
        self.process_apply(thread_id, parts)

class StatInfo:
    def __init__(self):
        self.latency_err_history = []
        self.latency_produce_ok_history = []
        self.latency_consume_ok_history = []
        self.latency_produce_err_history = []
        self.latency_consume_err_history = []
        self.faults = []
        self.recoveries = []


def render_overview(config, workload_dir, stat):
    latency_produce_log_path = os.path.join(workload_dir, "latency_produce_ok.log")
    latency_consume_log_path = os.path.join(workload_dir, "latency_consume_ok.log")
    latency_produce_err_log_path = os.path.join(workload_dir, "latency_produce_err.log")
    latency_consume_err_log_path = os.path.join(workload_dir, "latency_consume_err.log")
    throughput_log_path = os.path.join(workload_dir, "throughput.log")
    overview_gnuplot_path = os.path.join(workload_dir, "overview.gnuplot")

    try:
        latency_produce = open(latency_produce_log_path, "w")
        latency_consume = open(latency_consume_log_path, "w")
        latency_produce_err = open(latency_produce_err_log_path, "w")
        latency_consume_err = open(latency_consume_err_log_path, "w")
        throughput_log = open(throughput_log_path, "w")
        
        duration_ms = 0
        min_latency_us = None
        max_latency_us = 0
        max_unavailability_us = 0
        max_throughput = 0

        latencies = []
        for [ts_ms, latency_us] in stat.latency_produce_ok_history:
            latencies.append([ts_ms, latency_us])
        for [ts_ms, latency_us] in stat.latency_consume_ok_history:
            latencies.append([ts_ms, latency_us])
        latencies.sort(key=lambda x:x[0])
        last_ok = latencies[0][0]
        max_unavailability_ms = 0
        for [ts_ms,latency_us] in latencies:
            max_unavailability_ms = max(max_unavailability_ms, ts_ms - last_ok)
            last_ok = ts_ms
        max_unavailability_us = 1000 * max_unavailability_ms
        ops = len(latencies)
        throughput_builder = ThroughputBuilder()
        throughput_builder.build(config, latencies)

        latencies = []
        for [_, latency_us] in stat.latency_produce_ok_history:
            latencies.append(latency_us)
        latencies.sort()
        produce_p99  = latencies[int(0.99*len(latencies))]
        produce_min_latency_us = latencies[0]
        produce_max_latency_us = latencies[-1]

        latencies = []
        for [_, latency_us] in stat.latency_consume_ok_history:
            latencies.append(latency_us)
        latencies.sort()
        consume_p99  = latencies[int(0.99*len(latencies))]
        consume_min_latency_us = latencies[0]
        consume_max_latency_us = latencies[-1]
        
        for [ts_ms,latency_us] in stat.latency_produce_ok_history:
            duration_ms = max(duration_ms, ts_ms)
            latency_produce.write(f"{ts_ms}\t{latency_us}\n")
        
        for [ts_ms,latency_us] in stat.latency_consume_ok_history:
            duration_ms = max(duration_ms, ts_ms)
            latency_consume.write(f"{ts_ms}\t{latency_us}\n")
        
        for [ts_ms,latency_us] in stat.latency_produce_err_history:
            duration_ms = max(duration_ms, ts_ms)
            max_latency_us = max(max_latency_us, latency_us)
            latency_produce_err.write(f"{ts_ms}\t{latency_us}\n")
        
        for [ts_ms,latency_us] in stat.latency_consume_err_history:
            duration_ms = max(duration_ms, ts_ms)
            max_latency_us = max(max_latency_us, latency_us)
            latency_consume_err.write(f"{ts_ms}\t{latency_us}\n")
        
        for [ts_ms, count] in throughput_builder.total_throughput.history:
            duration_ms = max(duration_ms, ts_ms)
            max_throughput = max(max_throughput, count)
            throughput_log.write(f"{ts_ms}\t{count}\n")
        
        latency_produce.close()
        latency_consume.close()
        latency_produce_err.close()
        latency_consume_err.close()
        throughput_log.close()

        with open(overview_gnuplot_path, "w") as gnuplot_file:
            gnuplot_file.write(
                jinja2.Template(OVERVIEW).render(
                    title = config["name"],
                    duration=int(duration_ms/1000),
                    produce_big_latency=int(produce_p99*1.2),
                    consume_big_latency=int(consume_p99*1.2),
                    produce_p99=produce_p99,
                    consume_p99=consume_p99,
                    faults = stat.faults,
                    recoveries = stat.recoveries,
                    throughput=int(max_throughput*1.2)))
        
        gnuplot(overview_gnuplot_path, _cwd=workload_dir)

        return {
            "result": Result.PASSED,
            "latency_us": {
                "produce": {
                    "min": produce_min_latency_us,
                    "max": produce_max_latency_us,
                    "p99": produce_p99
                },
                "consume": {
                    "min": consume_min_latency_us,
                    "max": consume_max_latency_us,
                    "p99": consume_p99
                }
            },
            "max_unavailability_us": max_unavailability_us,
            "throughput": {
                "avg/s": int(float(1000 * ops) / duration_ms),
                "max/s": max_throughput
            }
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
        rm("-rf", latency_produce_log_path)
        rm("-rf", latency_consume_log_path)
        rm("-rf", latency_produce_err_log_path)
        rm("-rf", latency_consume_err_log_path)
        rm("-rf", throughput_log_path)
        rm("-rf", overview_gnuplot_path)

def collect(config, check, workload_dir):
    logger.setLevel(logging.DEBUG)
    logger_handler_path = os.path.join(workload_dir, "stat.log")
    handler = logging.FileHandler(logger_handler_path)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(handler)

    check["result"] = Result.PASSED
    total = StatInfo()
    for node in config["workload"]["nodes"]:
        node_dir = f"{workload_dir}/{node}"
        if os.path.isdir(node_dir):
            player = LogPlayer(config)

            with open(os.path.join(node_dir, "workload.log"), "r") as workload_file:
                last_line = None
                for line in workload_file:
                    if last_line != None:
                        player.apply(last_line)
                    last_line = line
            
            total.latency_produce_err_history.extend(player.latency_produce_err_history)
            total.latency_consume_err_history.extend(player.latency_consume_err_history)
            total.latency_produce_ok_history.extend(player.latency_produce_ok_history)
            total.latency_consume_ok_history.extend(player.latency_consume_ok_history)
            total.faults = player.faults
            total.recoveries = player.recoveries

            result = render_overview(config, node_dir, player)

            check[node] = result
        else:
            check[node] = {
                "result": Result.UNKNOWN,
                "message": f"Can't find logs dir: {workload_dir}"
            }
        check["result"] = Result.more_severe(check["result"], check[node]["result"])
    
    total.latency_produce_err_history.sort(key=lambda x:x[0])
    total.latency_consume_err_history.sort(key=lambda x:x[0])
    total.latency_produce_ok_history.sort(key=lambda x:x[0])
    total.latency_consume_ok_history.sort(key=lambda x:x[0])
    
    check["total"] = render_overview(config, workload_dir, total)
    check["result"] = Result.more_severe(check["result"], check["total"]["result"])
    
    handler.flush()
    handler.close()
    logger.removeHandler(handler)
    if check["result"] == Result.PASSED:
        rm("-rf", logger_handler_path)
    
    return check