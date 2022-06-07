from chaos.scenarios.single_topic_single_fault import SingleTopicSingleFault
from chaos.scenarios.tx_single_topic_single_fault import TxSingleTopicSingleFault
from chaos.scenarios.tx_money_single_fault import TxMoneySingleFault
from chaos.scenarios.tx_subscribe_single_fault import TxSubscribeSingleFault
from chaos.scenarios.rw_subscribe_single_fault import RWSubscribeSingleFault
from chaos.scenarios.tx_poll_single_fault import TxPollSingleFault

SCENARIOS = {
    "single_table_single_fault": SingleTopicSingleFault,
    "tx_single_table_single_fault": TxSingleTopicSingleFault,
    "tx_money_single_fault": TxMoneySingleFault,
    "tx_subscribe_single_fault": TxSubscribeSingleFault,
    "rw_subscribe_single_fault": RWSubscribeSingleFault,
    "tx_poll_single_fault": TxPollSingleFault
}