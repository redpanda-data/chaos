from chaos.faults.isolate_controller import IsolateControllerFault
from chaos.faults.isolate_follower import IsolateFollowerFault
from chaos.faults.isolate_leader import IsolateLeaderFault
from chaos.faults.kill_follower import KillFollowerFault
from chaos.faults.kill_leader import KillLeaderFault
from chaos.faults.leadership_transfer import LeadershipTransferFault
from chaos.faults.reconfigure_11_kill import Reconfigure11KillFault

FAULTS = {
    "isolate_controller": IsolateControllerFault,
    "isolate_follower": IsolateFollowerFault,
    "isolate_leader": IsolateLeaderFault,
    "kill_follower": KillFollowerFault,
    "kill_leader": KillLeaderFault,
    "leadership_transfer": LeadershipTransferFault,
    "reconfigure_11_kill": Reconfigure11KillFault
}