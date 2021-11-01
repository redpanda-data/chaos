from chaos.workloads.writing import writing

import logging

logger = logging.getLogger("chaos")

def kafka_clients_workload(nodes_path):
    writing_java = writing.Control()
    writing_java.launch = "/mnt/vectorized/control/writing.kafka-clients.start.sh"
    writing_java.alive = "/mnt/vectorized/control/writing.kafka-clients.alive.sh"
    writing_java.kill = "/mnt/vectorized/control/writing.kafka-clients.stop.sh"
    writing_java.name = "writing / kafka-clients"
    return writing.Workload(writing_java, nodes_path)

def confluent_kafka_workload(nodes_path):
    writing_python = writing.Control()
    writing_python.launch = "/mnt/vectorized/control/writing.confluent-kafka.start.sh"
    writing_python.alive = "/mnt/vectorized/control/writing.confluent-kafka.alive.sh"
    writing_python.kill = "/mnt/vectorized/control/writing.confluent-kafka.stop.sh"
    writing_python.name = "writing / confluent-kafka"
    return writing.Workload(writing_python, nodes_path)

WORKLOADS = {
    "writing / kafka-clients": kafka_clients_workload,
    "writing / confluent-kafka": confluent_kafka_workload
}

def wait_all_workloads_killed(nodes_path):
    for key in WORKLOADS:
        logger.debug(f"stopping workload {key} everywhere (if running)")
        workload_cluster = WORKLOADS[key](nodes_path)
        workload_cluster.kill_everywhere()
        workload_cluster.wait_killed(timeout_s = 10)