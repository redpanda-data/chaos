from sh import gnuplot, rm, cd
import jinja2
import sys
import traceback
import json
import os
from chaos.checks.result import Result
from chaos.workloads.tx_single_reads_writes.log_utils import State, cmds, transitions, phantoms
import logging

logger = logging.getLogger("stat")

LATENCY = """
set terminal png size 1600,1200
set output "percentiles.png"
set title "{{ title }}"
set multiplot
set yrange [0:{{ yrange }}]
set xrange [-0.1:1.1]

plot "percentiles.log" using 1:2 title "latency (us)" with line lt rgb "black",\\
     {{p99}} title "p99" with lines lt 1

unset multiplot
"""

AVAILABILITY = """
set terminal png size 1600,1200
set output "availability.png"
set title "{{ title }}"
show title
plot "availability.log" using ($1/1000):2 title "unavailability (us)" w p ls 7
"""

SEEN = """
set terminal png size 1600,1200
set output "seen.png"
set multiplot
set lmargin 6
set rmargin 10

set pointsize 0.2
set yrange [0:{{ seen_boundary }}]
set xrange [0:{{ duration }}]
set size 1, 1
set origin 0, 0

set title "write to read time"
show title

set parametric
{% for fault in faults %}plot [t=0:{{ seen_boundary }}] {{ fault }}/1000,t notitle lt rgb "red"
{% endfor %}{% for recovery in recoveries %}plot [t=0:{{ seen_boundary }}] {{ recovery }}/1000,t notitle lt rgb "blue"
{% endfor %}unset parametric

plot 'latency_seen.log' using ($1/1000):2 notitle with points lt rgb "black" pt 7,\\
     {{seen_p99}} title "p99" with lines lt 1

set notitle
unset multiplot
"""

OVERVIEW = """
set terminal png size 1600,1200
set output "overview.png"
set multiplot
set lmargin 6
set rmargin 10

set pointsize 0.2
set yrange [0:{{ commit_boundary }}]
set xrange [0:{{ duration }}]
set size 1, 0.2
set origin 0, 0

set title "commit time"
show title

set parametric
{% for fault in faults %}plot [t=0:{{ commit_boundary }}] {{ fault }}/1000,t notitle lt rgb "red"
{% endfor %}{% for recovery in recoveries %}plot [t=0:{{ commit_boundary }}] {{ recovery }}/1000,t notitle lt rgb "blue"
{% endfor %}unset parametric

plot 'latency_commit.log' using ($1/1000):2 notitle with points lt rgb "black" pt 7,\\
     {{commit_p99}} title "p99" with lines lt 1

set notitle

set y2range [0:{{ big_latency }}]
set yrange [0:{{ big_latency }}]
set size 1, 0.4
set origin 0, 0.2
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
     'latency_timeout.log' using ($1/1000):2 title "latency timeout (us)" with points lt rgb "blue" pt 7,\\
     {{p99}} title "p99" with lines lt 1

set title "{{ title }}"
show title

set yrange [0:{{ throughput }}]

set size 1, 0.4
set origin 0, 0.6
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
        self.time_us = 0

def collect(config, workload_dir):
    logger.setLevel(logging.DEBUG)
    logger_handler_path = os.path.join(workload_dir, "stat.log")
    handler = logging.FileHandler(logger_handler_path)
    handler.setFormatter(logging.Formatter("%(asctime)s - %(message)s"))
    logger.addHandler(handler)
    
    percentiles_log_path = os.path.join(workload_dir, "percentiles.log")
    latency_commit_log_path = os.path.join(workload_dir, "latency_commit.log")
    latency_seen_log_path = os.path.join(workload_dir, "latency_seen.log")
    latency_ok_log_path = os.path.join(workload_dir, "latency_ok.log")
    latency_err_log_path = os.path.join(workload_dir, "latency_err.log")
    latency_timeout_log_path = os.path.join(workload_dir, "latency_timeout.log")
    throughput_log_path = os.path.join(workload_dir, "throughput.log")
    availability_log_path = os.path.join(workload_dir, "availability.log")

    workload_log_path = os.path.join(workload_dir, "workload.log")

    overview_gnuplot_path = os.path.join(workload_dir, "overview.gnuplot")
    availability_gnuplot_path = os.path.join(workload_dir, "availability.gnuplot")
    percentiles_gnuplot_path = os.path.join(workload_dir, "percentiles.gnuplot")
    seen_gnuplot_path = os.path.join(workload_dir, "seen.gnuplot")

    has_errors = True

    try:
        percentiles = open(percentiles_log_path, "w")
        latency_ok = open(latency_ok_log_path, "w")
        latency_err = open(latency_err_log_path, "w")
        latency_timeout = open(latency_timeout_log_path, "w")
        latency_commit = open(latency_commit_log_path, "w")
        latency_seen = open(latency_seen_log_path, "w")
        throughput_log = open(throughput_log_path, "w")
        availability_log = open(availability_log_path, "w")

        last_state = dict()
        last_time = None

        throughput = dict()

        faults = []
        recoveries = []
        info = None

        latency_seen_history = []
        latency_ok_history = []
        latency_err_history = []
        latency_timeout_history = []
        latency_commit_history = []
        availability_history = []
        throughput_history = []
        throughput_bucket = None

        should_measure = False
        started = None

        def tick(now, throughput_history):
            while throughput_bucket.time_us + 1000000 < now:
                if should_measure:
                    ts = int((throughput_bucket.time_us-started+1000000)/1000)
                    throughput_history.append([ts, throughput_bucket.count])
                throughput_bucket.count = 0
                throughput_bucket.time_us += 1000000

        with open(workload_log_path, "r") as workload_file:
            last_ok = None
            attempt_starts = {}
            commit_starts = {}
            is_end_commit = {}

            for line in workload_file:
                parts = line.rstrip().split('\t')

                thread_id = int(parts[0])
                if thread_id not in last_state:
                    last_state[thread_id] = State.INIT
                if thread_id not in attempt_starts:
                    attempt_starts[thread_id] = None

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
                        throughput_bucket = Throughput()
                        throughput_bucket.time_us = ts_us
                    else:
                        delta_us = int(parts[1])
                        ts_us = last_time + delta_us
                    last_time = ts_us
                elif new_state == State.CONSTRUCTING:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    attempt_starts[thread_id] = last_time + delta_us
                    tick(attempt_starts[thread_id], throughput_history)
                    last_time = attempt_starts[thread_id]
                elif new_state == State.CONSTRUCTED:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    end = last_time + delta_us
                    tick(end, throughput_history)
                    last_time = end
                elif new_state == State.TX:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    attempt_starts[thread_id] = last_time + delta_us
                    tick(attempt_starts[thread_id], throughput_history)
                    last_time = attempt_starts[thread_id]
                elif new_state == State.COMMIT or new_state == State.ABORT:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    end = last_time + delta_us
                    tick(end, throughput_history)
                    last_time = end
                    if new_state == State.COMMIT:
                        commit_starts[thread_id] = last_time
                        is_end_commit[thread_id] = True
                    if new_state == State.ABORT:
                        is_end_commit[thread_id] = False
                elif new_state == State.OK:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    end = last_time + delta_us
                    tick(end, throughput_history)
                    throughput_bucket.count+=1
                    last_time = end
                    if last_ok == None:
                        last_ok = end
                    if should_measure:
                        if is_end_commit[thread_id]:
                            availability_history.append([int((end-started)/1000), end-last_ok])
                            latency_ok_history.append([int((end-started)/1000), end-attempt_starts[thread_id]])
                            latency_commit_history.append([int((end-started)/1000), end-commit_starts[thread_id]])
                            del commit_starts[thread_id]
                        else:
                            latency_err_history.append([int((end-started)/1000), end-attempt_starts[thread_id]])
                    last_ok = end
                    del is_end_commit[thread_id]
                elif new_state == State.ERROR:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    end = last_time + delta_us
                    tick(end, throughput_history)
                    last_time = end
                    if should_measure:
                        latency_err_history.append([int((end-started)/1000), end-attempt_starts[thread_id]])
                    if thread_id in is_end_commit:
                        del is_end_commit[thread_id]
                elif new_state == State.EVENT:
                    ts_us = None
                    if last_time == None:
                        ts_us = int(parts[1])
                        throughput_bucket = Throughput()
                        throughput_bucket.time_us = ts_us
                    else:
                        delta_us = int(parts[1])
                        ts_us = last_time + delta_us
                    last_time = ts_us
                    name = parts[3]
                    if name == "measure" and not should_measure:
                        should_measure = True
                        started = ts_us
                        last_ok = ts_us
                    if should_measure:
                        if name=="injecting" or name=="injected":
                            faults.append(int((ts_us - started)/1000))
                        elif name=="healing" or name=="healed":
                            recoveries.append(int((ts_us - started)/1000))
                elif new_state == State.SEEN:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    end = last_time + delta_us
                    tick(end, throughput_history)
                    last_time = end
                    seen_us = int(parts[3])
                    if should_measure:
                        latency_seen_history.append([int((end-started)/1000), seen_us])
                elif new_state == State.VIOLATION or new_state == State.LOG:
                    if last_time == None:
                        raise Exception(f"last_time can't be None when processing: {new_state}")
                    delta_us = int(parts[1])
                    end = last_time + delta_us
                    tick(end, throughput_history)
                    last_time = end
                else:
                    raise Exception(f"unknown state: {new_state}")

        duration_ms = 0
        max_latency_us = 0
        min_latency_us = None
        max_throughput = 0
        max_unavailability_us = 0
        ops = len(latency_ok_history)

        latencies = []
        for [_, latency_us] in latency_ok_history:
            latencies.append(latency_us)
        latencies.sort()
        p99  = latencies[int(0.99*len(latencies))]
        for i in range(0,len(latencies)):
            percentiles.write(f"{float(i) / len(latencies)}\t{latencies[i]}\n")

        latencies = []
        for [_, latency_us] in latency_commit_history:
            latencies.append(latency_us)
        latencies.sort()
        commit_p99 = latencies[int(0.99*len(latencies))]
        commit_min = latencies[0]
        commit_max = latencies[-1]

        latencies = []
        for [_, latency_us] in latency_seen_history:
            latencies.append(latency_us)
        latencies.sort()
        seen_p99 = latencies[int(0.99*len(latencies))]
        seen_min = latencies[0]
        seen_max = latencies[-1]
        
        for [ts_ms,latency_us] in latency_seen_history:
            duration_ms = max(duration_ms, ts_ms)
            latency_seen.write(f"{ts_ms}\t{latency_us}\n")
        
        for [ts_ms,latency_us] in latency_commit_history:
            duration_ms = max(duration_ms, ts_ms)
            latency_commit.write(f"{ts_ms}\t{latency_us}\n")

        for [ts_ms,latency_us] in latency_ok_history:
            duration_ms = max(duration_ms, ts_ms)
            if min_latency_us == None:
                min_latency_us = latency_us
            min_latency_us = min(min_latency_us, latency_us)
            max_latency_us = max(max_latency_us, latency_us)
            latency_ok.write(f"{ts_ms}\t{latency_us}\n")

        for [ts_ms,latency_us] in latency_err_history:
            duration_ms = max(duration_ms, ts_ms)
            max_latency_us = max(max_latency_us, latency_us)
            latency_err.write(f"{ts_ms}\t{latency_us}\n")

        for [ts_ms,latency_us] in latency_timeout_history:
            duration_ms = max(duration_ms, ts_ms)
            max_latency_us = max(max_latency_us, latency_us)
            latency_timeout.write(f"{ts_ms}\t{latency_us}\n")

        for [ts_ms,latency_us] in availability_history:
            max_unavailability_us = max(max_unavailability_us, latency_us)
            availability_log.write(f"{ts_ms}\t{latency_us}\n")

        for [ts_ms, count] in throughput_history:
            duration_ms = max(duration_ms, ts_ms)
            max_throughput = max(max_throughput, count)
            throughput_log.write(f"{ts_ms}\t{count}\n")

        latency_ok.close()
        latency_err.close()
        latency_timeout.close()
        latency_commit.close()
        throughput_log.close()
        availability_log.close()

        with open(overview_gnuplot_path, "w") as gnuplot_file:
            gnuplot_file.write(
                jinja2.Template(OVERVIEW).render(
                    title = config["name"],
                    duration=int(duration_ms/1000),
                    big_latency=int(p99*1.2),
                    p99=p99,
                    commit_p99=commit_p99,
                    commit_boundary=int(commit_p99*1.2), 
                    faults = faults,
                    recoveries = recoveries,
                    throughput=int(max_throughput*1.2)))
        
        with open(seen_gnuplot_path, "w") as gnuplot_file:
            gnuplot_file.write(
                jinja2.Template(SEEN).render(
                    title = config["name"],
                    duration=int(duration_ms/1000),
                    seen_p99=seen_p99,
                    seen_boundary=int(seen_p99*1.2), 
                    faults = faults,
                    recoveries = recoveries))

        with open(availability_gnuplot_path, "w") as gnuplot_file:
            gnuplot_file.write(jinja2.Template(AVAILABILITY).render(
                title = config["name"]))

        with open(percentiles_gnuplot_path, "w") as latency_file:
            latency_file.write(jinja2.Template(LATENCY).render(
                title = config["name"],
                yrange = int(p99*1.2),
                p99 = p99))

        gnuplot(overview_gnuplot_path, _cwd=workload_dir)
        gnuplot(availability_gnuplot_path, _cwd=workload_dir)
        gnuplot(percentiles_gnuplot_path, _cwd=workload_dir)
        gnuplot(seen_gnuplot_path, _cwd=workload_dir)

        has_errors = False

        return {
            "result": Result.PASSED,
            "latency_us": {
                "tx": {
                    "min": min_latency_us,
                    "max": max_latency_us,
                    "p99": p99
                },
                "commit": {
                    "min": commit_min,
                    "max": commit_max,
                    "p99": commit_p99
                },
                "write-to-read": {
                    "min": seen_min,
                    "max": seen_max,
                    "p99": seen_p99
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
        handler.flush()
        handler.close()
        logger.removeHandler(handler)

        if not has_errors:
            rm("-rf", logger_handler_path)

        rm("-rf", percentiles_log_path)
        rm("-rf", latency_ok_log_path)
        rm("-rf", latency_err_log_path)
        rm("-rf", latency_timeout_log_path)
        rm("-rf", throughput_log_path)
        rm("-rf", availability_log_path)
        rm("-rf", overview_gnuplot_path)
        rm("-rf", seen_gnuplot_path)
        rm("-rf", availability_gnuplot_path)
        rm("-rf", percentiles_gnuplot_path)
        rm("-rf", latency_commit_log_path)
        rm("-rf", latency_seen_log_path)