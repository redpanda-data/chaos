from chaos.scenarios.single_topic_single_fault import SingleTopicSingleFault
from chaos.scenarios.tx_single_topic_single_fault import TxSingleTopicSingleFault

SCENARIOS = {
    "single_table_single_fault": SingleTopicSingleFault,
    "tx_single_table_single_fault": TxSingleTopicSingleFault
}