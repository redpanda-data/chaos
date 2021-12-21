from chaos.scenarios.single_topic_single_fault import SingleTopicSingleFault
from chaos.scenarios.tx_single_topic_single_fault import TxSingleTopicSingleFault
from chaos.scenarios.tx_money_single_fault import TxMoneySingleFault
from chaos.scenarios.tx_streaming_single_fault import TxStreamingSingleFault
from chaos.scenarios.tx_subscribe_single_fault import TxSubscribeSingleFault

SCENARIOS = {
    "single_table_single_fault": SingleTopicSingleFault,
    "tx_single_table_single_fault": TxSingleTopicSingleFault,
    "tx_money_single_fault": TxMoneySingleFault,
    "tx_streaming_single_fault": TxStreamingSingleFault,
    "tx_subscribe_single_fault": TxSubscribeSingleFault
}