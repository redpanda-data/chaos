from chaos.scenarios.single_topic_single_fault import SingleTopicSingleFault
from chaos.scenarios.tx_single_topic_single_fault import TxSingleTopicSingleFault
from chaos.scenarios.tx_money_single_fault import TxMoneySingleFault

SCENARIOS = {
    "single_table_single_fault": SingleTopicSingleFault,
    "tx_single_table_single_fault": TxSingleTopicSingleFault,
    "tx_money_single_fault": TxMoneySingleFault
}