from enum import Enum

class State(Enum):
    STARTED = 0
    CONSTRUCTING = 1
    CONSTRUCTED = 2
    SENDING = 3
    OK = 4
    ERROR = 5
    TIMEOUT = 6
    EVENT = 7
    VIOLATION = 8
    LOG = 9

cmds = {
    "started": State.STARTED,
    "constructing": State.CONSTRUCTING,
    "constructed": State.CONSTRUCTED,
    "msg": State.SENDING,
    "ok": State.OK,
    "err": State.ERROR,
    "time": State.TIMEOUT,
    "event": State.EVENT,
    "violation": State.VIOLATION,
    "log": State.LOG
}

transitions = {
    State.STARTED: [State.CONSTRUCTING],
    State.CONSTRUCTING: [State.CONSTRUCTED, State.ERROR],
    State.CONSTRUCTED: [State.SENDING, State.CONSTRUCTING],
    State.SENDING: [State.OK, State.ERROR, State.TIMEOUT],
    State.OK: [State.SENDING, State.CONSTRUCTING],
    State.ERROR: [State.SENDING, State.CONSTRUCTING],
    State.TIMEOUT: [State.SENDING, State.CONSTRUCTING]
}

phantoms = [ State.EVENT, State.VIOLATION, State.LOG ]