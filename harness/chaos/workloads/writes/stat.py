from sh import gnuplot, rm, cd
import jinja2
import sys
import traceback
import json
import os
from chaos.checks.result import Result
from chaos.workloads.writes.log_utils import State, cmds, transitions, phantoms
import logging

logger = logging.getLogger("stat")

LATENCY = """
set terminal png size 1600,1200
set output "percentiles.png"
set title "{{ title }}"
set multiplot
set yrange [0:{{ yrange }}]
set xrange [-0.1:1.1]

plot "percentiles.log" using 1:2 title "latency (us)" with line lt rgb "black"

set label at 0.9, {{ p99 }} 'p99'

plot '-' using 1:2 notitle with points pt 2 lc 1
0.99 {{ p99 }}
EOF

unset multiplot
"""

AVAILABILITY = """
set terminal png size 1600,1200
set output "availability.png"
set title "{{ title }}"
show title
plot "availability.log" using ($1/1000):2 title "unavailability (us)" w p ls 7
"""

OVERVIEW = """
set terminal png size 1600,1200
set output "overview.png"
set multiplot
set lmargin 6
set rmargin 10

set pointsize 0.2
set xrange [0:{{ duration }}]

set y2range [0:{{ big_latency }}]
set yrange [0:{{ big_latency }}]
set size 1, 0.5
set origin 0, 0
unset ytics
set y2tics auto
set tmargin 0
set border 11

set parametric
{% for fault in faults %}plot [t=0:{{ big_latency }}] {{ fault }}/1000,t notitle lt rgb "red"
{% endfor %}{% for recovery in recoveries %}plot [t=0:{{ big_latency }}] {{ recovery }}/1000,t notitle lt rgb "blue"
{% endfor %}unset parametric

plot 'latency_ok.log' using ($1/1000):2 title "latency ok (us)" with points lt rgb "black" pt 7,\\
     'latency_err.log' using ($1/1000):2 title "latency err (us)" with points lt rgb "red" pt 7,\\
     {{p99}} title "p99" with lines lt 1

set title "{{ title }}"
show title

set yrange [0:{{ throughput }}]

set size 1, 0.5
set origin 0, 0.5
set format x ""
set bmargin 0
set tmargin 3
set border 15
unset y2tics
set ytics

set parametric
{% for fault in faults %}plot [t=0:{{ throughput }}] {{ fault }}/1000,t notitle lt rgb "red"
{% endfor %}{% for recovery in recoveries %}plot [t=0:{{ throughput }}] {{ recovery }}/1000,t notitle lt rgb "blue"
{% endfor %}unset parametric

plot 'throughput.log' using ($1/1000):2 title "throughput (1s)" with line lt rgb "black"

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
        self.partition_throughput = dict()
    
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

        self.latency_err_history = []
        self.latency_ok_history = []
        self.faults = []
        self.recoveries = []

        self.op_started = dict()

        self.should_measure = False
    
    def writing_apply(self, thread_id, parts):
        if self.curr_state[thread_id] == State.CONSTRUCTING:
            self.op_started[thread_id] = self.ts_us
        elif self.curr_state[thread_id] == State.SENDING:
            self.op_started[thread_id] = self.ts_us
        elif self.curr_state[thread_id] == State.CONSTRUCTED:
            del self.op_started[thread_id]
        elif self.curr_state[thread_id] in [State.TIMEOUT, State.ERROR]:
            if self.should_measure:
                self.latency_err_history.append([int((self.ts_us-self.started_us)/1000), self.ts_us-self.op_started[thread_id]])
            del self.op_started[thread_id]
        elif self.curr_state[thread_id] == State.OK:
            if self.should_measure:
                self.latency_ok_history.append([int((self.ts_us-self.started_us)/1000), self.ts_us-self.op_started[thread_id]])
    
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

        self.writing_apply(thread_id, parts)

class StatInfo:
    def __init__(self):
        self.latency_err_history = []
        self.latency_ok_history = []
        self.faults = []
        self.recoveries = []

def render_overview(config, workload_dir, stat):
    latency_ok_log_path = os.path.join(workload_dir, "latency_ok.log")
    latency_err_log_path = os.path.join(workload_dir, "latency_err.log")
    throughput_log_path = os.path.join(workload_dir, "throughput.log")
    overview_gnuplot_path = os.path.join(workload_dir, "overview.gnuplot")

    try:
        latency_ok = open(latency_ok_log_path, "w")
        latency_err = open(latency_err_log_path, "w")
        throughput_log = open(throughput_log_path, "w")
        
        duration_ms = 0
        min_latency_us = None
        max_latency_us = 0
        max_unavailability_us = 0
        max_throughput = 0
        p99 = None

        latencies = []
        for [_, latency_us] in stat.latency_ok_history:
            latencies.append(latency_us)
        latencies.sort()
        p99  = latencies[int(0.99*len(latencies))]

        max_unavailability_ms = 0
        last_ok = stat.latency_ok_history[0][0]
        for [ts_ms,latency_us] in stat.latency_ok_history:
            max_unavailability_ms = max(max_unavailability_ms, ts_ms - last_ok)
            last_ok = ts_ms
            duration_ms = max(duration_ms, ts_ms)
            if min_latency_us == None:
                min_latency_us = latency_us
            min_latency_us = min(min_latency_us, latency_us)
            max_latency_us = max(max_latency_us, latency_us)
            latency_ok.write(f"{ts_ms}\t{latency_us}\n")
        max_unavailability_us = 1000 * max_unavailability_ms
        
        for [ts_ms,latency_us] in stat.latency_err_history:
            duration_ms = max(duration_ms, ts_ms)
            max_latency_us = max(max_latency_us, latency_us)
            latency_err.write(f"{ts_ms}\t{latency_us}\n")
        
        throughput_builder = ThroughputBuilder()
        throughput_builder.build(config, stat.latency_ok_history)
        
        for [ts_ms, count] in throughput_builder.total_throughput.history:
            duration_ms = max(duration_ms, ts_ms)
            max_throughput = max(max_throughput, count)
            throughput_log.write(f"{ts_ms}\t{count}\n")
        
        latency_ok.close()
        latency_err.close()
        throughput_log.close()
        
        with open(overview_gnuplot_path, "w") as gnuplot_file:
            gnuplot_file.write(
                jinja2.Template(OVERVIEW).render(
                    title = config["name"],
                    duration=int(duration_ms/1000),
                    big_latency=int(p99*1.2),
                    p99=p99,
                    faults = stat.faults,
                    recoveries = stat.recoveries,
                    throughput=int(max_throughput*1.2)))
        
        gnuplot(overview_gnuplot_path, _cwd=workload_dir)
        ops = len(stat.latency_ok_history)

        return {
            "result": Result.PASSED,
            "latency_us": {
                "tx": {
                    "min": min_latency_us,
                    "max": max_latency_us,
                    "p99": p99
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
        rm("-rf", latency_ok_log_path)
        rm("-rf", latency_err_log_path)
        rm("-rf", throughput_log_path)
        rm("-rf", overview_gnuplot_path)

def render_availability(config, workload_dir, stat):
    availability_log_path = os.path.join(workload_dir, "availability.log")
    availability_gnuplot_path = os.path.join(workload_dir, "availability.gnuplot")

    try:
        availability_log = open(availability_log_path, "w")

        last_ok = stat.latency_ok_history[0][0]
        for [ts_ms,latency_us] in stat.latency_ok_history:
            availability_log.write(f"{ts_ms}\t{1000 * (ts_ms - last_ok)}\n")
            last_ok = ts_ms
        
        availability_log.close()
        
        with open(availability_gnuplot_path, "w") as gnuplot_file:
            gnuplot_file.write(jinja2.Template(AVAILABILITY).render(
                title = config["name"]))

        gnuplot(availability_gnuplot_path, _cwd=workload_dir)
    except:
        e, v = sys.exc_info()[:2]
        trace = traceback.format_exc()
        logger.debug(v)
        logger.debug(trace)
    finally:
        rm("-rf", availability_log_path)
        rm("-rf", availability_gnuplot_path)

def render_percentiles(config, workload_dir, stat):
    percentiles_log_path = os.path.join(workload_dir, "percentiles.log")
    percentiles_gnuplot_path = os.path.join(workload_dir, "percentiles.gnuplot")

    try:
        percentiles = open(percentiles_log_path, "w")

        latencies = []
        for [_, latency_us] in stat.latency_ok_history:
            latencies.append(latency_us)
        latencies.sort()
        p99  = latencies[int(0.99*len(latencies))]
        for i in range(0,len(latencies)):
            percentiles.write(f"{float(i) / len(latencies)}\t{latencies[i]}\n")
        
        percentiles.close()
        
        with open(percentiles_gnuplot_path, "w") as latency_file:
            latency_file.write(jinja2.Template(LATENCY).render(
                title = config["name"],
                yrange = int(p99*1.2),
                p99 = p99))

        gnuplot(percentiles_gnuplot_path, _cwd=workload_dir)
    except:
        e, v = sys.exc_info()[:2]
        trace = traceback.format_exc()
        logger.debug(v)
        logger.debug(trace)
    finally:
        rm("-rf", percentiles_log_path)
        rm("-rf", percentiles_gnuplot_path)

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
            
            total.latency_err_history.extend(player.latency_err_history)
            total.latency_ok_history.extend(player.latency_ok_history)
            total.faults = player.faults
            total.recoveries = player.recoveries

            result = render_overview(config, node_dir, player)
            render_availability(config, node_dir, player)
            render_percentiles(config, node_dir, player)

            check[node] = result
        else:
            check[node] = {
                "result": Result.UNKNOWN,
                "message": f"Can't find logs dir: {workload_dir}"
            }
        check["result"] = Result.more_severe(check["result"], check[node]["result"])
    
    total.latency_err_history.sort(key=lambda x:x[0])
    total.latency_ok_history.sort(key=lambda x:x[0])
    
    check["total"] = render_overview(config, workload_dir, total)
    check["result"] = Result.more_severe(check["result"], check["total"]["result"])
    
    handler.flush()
    handler.close()
    logger.removeHandler(handler)
    if check["result"] == Result.PASSED:
        rm("-rf", logger_handler_path)
    
    return check