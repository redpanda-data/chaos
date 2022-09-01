from time import sleep
import logging
from chaos.faults.types import FaultType
from confluent_kafka import Producer
from confluent_kafka import KafkaException

logger = logging.getLogger("chaos")

class HijackTxIDsFault:
    def __init__(self, fault_config):
        self.fault_type = FaultType.ONEOFF
        self.fault_config = fault_config
        self.name = "hijack tx ids"

    def execute(self, scenario):
        for tx_id in self.fault_config["ids"]:
            attempt = 0
            while True:
                logger.debug(f"hijacking {tx_id}")
                try:
                    producer = Producer({
                        "bootstrap.servers": scenario.config["brokers"],
                        "topic.metadata.refresh.interval.ms": 5000,
                        "metadata.max.age.ms": 10000,
                        "topic.metadata.refresh.fast.interval.ms": 250,
                        "topic.metadata.propagation.max.ms": 10000,
                        "socket.timeout.ms": 10000,
                        "connections.max.idle.ms": 0,
                        "reconnect.backoff.ms": 100,
                        "reconnect.backoff.max.ms": 10000,
                        "statistics.interval.ms": 0,
                        "api.version.request.timeout.ms": 10000,
                        "api.version.fallback.ms": 0,
                        "queue.buffering.max.ms": 0,
                        "retry.backoff.ms": 100,
                        "sticky.partitioning.linger.ms": 10,
                        "message.timeout.ms": 10000,
                        "request.required.acks": -1,
                        "retries": 5,
                        "enable.idempotence": True,
                        "transactional.id": tx_id
                    })
                    producer.init_transactions()
                    return
                except KafkaException as e:
                    if attempt > 6:
                        raise e
                attempt += 1
                if attempt % 2 == 0:
                    sleep(1)
