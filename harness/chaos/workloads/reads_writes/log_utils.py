from enum import Enum

class State(Enum):
    INIT = 0
    STARTED = 1
    CONSTRUCTING = 2
    CONSTRUCTED = 3
    SENDING = 4
    OK = 5
    ERROR = 6
    TIMEOUT = 7
    EVENT = 8
    VIOLATION = 9
    WRITTEN = 10

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
    "written": State.WRITTEN
}

transitions = {
    State.INIT: [State.STARTED],
    State.STARTED: [State.CONSTRUCTING],
    State.CONSTRUCTING: [State.CONSTRUCTED, State.ERROR],
    State.CONSTRUCTED: [State.SENDING, State.CONSTRUCTING],
    State.SENDING: [State.OK, State.ERROR, State.TIMEOUT],
    State.OK: [State.SENDING, State.CONSTRUCTING],
    State.ERROR: [State.SENDING, State.CONSTRUCTING],
    State.TIMEOUT: [State.SENDING, State.CONSTRUCTING]
}

phantoms = [ State.EVENT, State.VIOLATION, State.WRITTEN ]