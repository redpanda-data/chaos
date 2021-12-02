from chaos.faults.isolate_controller import IsolateControllerFault
from chaos.faults.isolate_follower import IsolateFollowerFault
from chaos.faults.isolate_leader import IsolateLeaderFault
from chaos.faults.isolate_tx_leader import IsolateTxLeaderFault
from chaos.faults.isolate_tx_follower import IsolateTxFollowerFault
from chaos.faults.isolate_all import IsolateAllFault
from chaos.faults.kill_follower import KillFollowerFault
from chaos.faults.kill_leader import KillLeaderFault
from chaos.faults.kill_tx_leader import KillTxLeaderFault
from chaos.faults.kill_tx_follower import KillTxFollowerFault
from chaos.faults.kill_all import KillAllFault
from chaos.faults.pause_follower import PauseFollowerFault
from chaos.faults.pause_leader import PauseLeaderFault
from chaos.faults.leadership_transfer import LeadershipTransferFault
from chaos.faults.reconfigure_11_kill import Reconfigure11KillFault
from chaos.faults.reconfigure_313 import Reconfigure313Fault
from chaos.faults.reconfigure_kill_11 import ReconfigureKill11Fault
from chaos.faults.isolate_clients_kill_leader import IsolateClientsKillLeader
from chaos.faults.rolling_restart import RollingRestartFault

FAULTS = {
    "isolate_controller": IsolateControllerFault,
    "isolate_follower": IsolateFollowerFault,
    "isolate_leader": IsolateLeaderFault,
    "isolate_tx_leader": IsolateTxLeaderFault,
    "isolate_tx_follower": IsolateTxFollowerFault,
    "isolate_all": IsolateAllFault,
    "isolate_clients_kill_leader": IsolateClientsKillLeader,
    "kill_follower": KillFollowerFault,
    "kill_leader": KillLeaderFault,
    "kill_tx_leader": KillTxLeaderFault,
    "kill_tx_follower": KillTxFollowerFault,
    "kill_all": KillAllFault,
    "pause_follower": PauseFollowerFault,
    "pause_leader": PauseLeaderFault,
    "leadership_transfer": LeadershipTransferFault,
    "reconfigure_11_kill": Reconfigure11KillFault,
    "reconfigure_313": Reconfigure313Fault,
    "reconfigure_kill_11": ReconfigureKill11Fault,
    "rolling_restart": RollingRestartFault
}