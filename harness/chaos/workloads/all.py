from chaos.workloads.writes import writes
from chaos.workloads.reads_writes import reads_writes
from chaos.workloads.tx_single_reads_writes import tx_single_reads_writes
from chaos.workloads.tx_money import tx_money
from chaos.workloads.tx_subscribe import tx_subscribe
from chaos.workloads.rw_subscribe import rw_subscribe
from chaos.workloads.tx_poll import tx_poll

import logging

logger = logging.getLogger("chaos")

def list_offsets_workload(nodes_path):
    writing_java = writes.Control()
    writing_java.launch = "/mnt/vectorized/control/list-offsets.java.start.sh"
    writing_java.alive = "/mnt/vectorized/control/list-offsets.java.alive.sh"
    writing_java.kill = "/mnt/vectorized/control/list-offsets.java.stop.sh"
    writing_java.name = "list-offsets / java"
    return writes.Workload(writing_java, nodes_path)

def reads_writes_workload(nodes_path):
    control = reads_writes.Control()
    control.launch = "/mnt/vectorized/control/reads-writes.java.start.sh"
    control.alive = "/mnt/vectorized/control/reads-writes.java.alive.sh"
    control.kill = "/mnt/vectorized/control/reads-writes.java.stop.sh"
    control.name = "reads-writes / java"
    return reads_writes.Workload(control, nodes_path)

def rw_subscribe_workload(nodes_path):
    writing_java = tx_subscribe.Control()
    writing_java.launch = "/mnt/vectorized/control/rw-subscribe.java.start.sh"
    writing_java.alive = "/mnt/vectorized/control/rw-subscribe.java.alive.sh"
    writing_java.kill = "/mnt/vectorized/control/rw-subscribe.java.stop.sh"
    writing_java.name = "rw-subscribe / java"
    return rw_subscribe.Workload(writing_java, nodes_path)

def tx_single_reads_writes_workload(nodes_path):
    writing_java = tx_single_reads_writes.Control()
    writing_java.launch = "/mnt/vectorized/control/tx-single-reads-writes.java.start.sh"
    writing_java.alive = "/mnt/vectorized/control/tx-single-reads-writes.java.alive.sh"
    writing_java.kill = "/mnt/vectorized/control/tx-single-reads-writes.java.stop.sh"
    writing_java.name = "tx-single-reads-writes / java"
    return tx_single_reads_writes.Workload(writing_java, nodes_path)

def tx_money_workload(nodes_path):
    writing_java = tx_money.Control()
    writing_java.launch = "/mnt/vectorized/control/tx-money.java.start.sh"
    writing_java.alive = "/mnt/vectorized/control/tx-money.java.alive.sh"
    writing_java.kill = "/mnt/vectorized/control/tx-money.java.stop.sh"
    writing_java.name = "tx-money / java"
    return tx_money.Workload(writing_java, nodes_path)

def tx_subscribe_workload(nodes_path):
    writing_java = tx_subscribe.Control()
    writing_java.launch = "/mnt/vectorized/control/tx-subscribe.java.start.sh"
    writing_java.alive = "/mnt/vectorized/control/tx-subscribe.java.alive.sh"
    writing_java.kill = "/mnt/vectorized/control/tx-subscribe.java.stop.sh"
    writing_java.name = "tx-subscribe / java"
    return tx_subscribe.Workload(writing_java, nodes_path)

def tx_poll_workload(nodes_path):
    writing_java = tx_poll.Control()
    writing_java.launch = "/mnt/vectorized/control/tx-poll.java.start.sh"
    writing_java.alive = "/mnt/vectorized/control/tx-poll.java.alive.sh"
    writing_java.kill = "/mnt/vectorized/control/tx-poll.java.stop.sh"
    writing_java.name = "tx-poll / java"
    return tx_poll.Workload(writing_java, nodes_path)

WORKLOADS = {
    "tx-single-reads-writes / java": tx_single_reads_writes_workload,
    "reads-writes / java": reads_writes_workload,
    "rw-subscribe / java": rw_subscribe_workload,
    "list-offsets / java": list_offsets_workload,
    "tx-money / java": tx_money_workload,
    "tx-subscribe / java": tx_subscribe_workload,
    "tx-poll / java": tx_poll_workload
}

def wait_all_workloads_killed(nodes_path):
    for key in WORKLOADS:
        logger.debug(f"stopping workload {key} everywhere (if running)")
        workload_cluster = WORKLOADS[key](nodes_path)
        workload_cluster.kill_everywhere()
        workload_cluster.wait_killed(timeout_s = 10)