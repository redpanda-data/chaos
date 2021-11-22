from chaos.workloads.writing import writing

import logging

logger = logging.getLogger("chaos")

def kafka_clients_workload(nodes_path):
    writing_java = writing.Control()
    writing_java.launch = "/mnt/vectorized/control/writing.kafka-clients.start.sh"
    writing_java.alive = "/mnt/vectorized/control/writing.kafka-clients.alive.sh"
    writing_java.kill = "/mnt/vectorized/control/writing.kafka-clients.stop.sh"
    writing_java.name = "writes / kafka-clients"
    return writing.Workload(writing_java, nodes_path)

def confluent_kafka_workload(nodes_path):
    writing_python = writing.Control()
    writing_python.launch = "/mnt/vectorized/control/writing.confluent-kafka.start.sh"
    writing_python.alive = "/mnt/vectorized/control/writing.confluent-kafka.alive.sh"
    writing_python.kill = "/mnt/vectorized/control/writing.confluent-kafka.stop.sh"
    writing_python.name = "writes / confluent-kafka"
    return writing.Workload(writing_python, nodes_path)

def list_offsets_workload(nodes_path):
    writing_java = writing.Control()
    writing_java.launch = "/mnt/vectorized/control/writing.list-offsets.start.sh"
    writing_java.alive = "/mnt/vectorized/control/writing.list-offsets.alive.sh"
    writing_java.kill = "/mnt/vectorized/control/writing.list-offsets.stop.sh"
    writing_java.name = "list-offsets / java"
    return writing.Workload(writing_java, nodes_path)

def reads_writes_workload(nodes_path):
    reads_writes = writing.Control()
    reads_writes.launch = "/mnt/vectorized/control/writing.reads-writes.start.sh"
    reads_writes.alive = "/mnt/vectorized/control/writing.reads-writes.alive.sh"
    reads_writes.kill = "/mnt/vectorized/control/writing.reads-writes.stop.sh"
    reads_writes.name = "reads-writes / java"
    return writing.Workload(reads_writes, nodes_path)

WORKLOADS = {
    "reads-writes / java": reads_writes_workload,
    "list-offsets / java": list_offsets_workload,
    "writes / kafka-clients": kafka_clients_workload,
    "writes / confluent-kafka": confluent_kafka_workload
}

def wait_all_workloads_killed(nodes_path):
    for key in WORKLOADS:
        logger.debug(f"stopping workload {key} everywhere (if running)")
        workload_cluster = WORKLOADS[key](nodes_path)
        workload_cluster.kill_everywhere()
        workload_cluster.wait_killed(timeout_s = 10)