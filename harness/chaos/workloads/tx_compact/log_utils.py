from enum import Enum

class State(Enum):
    INIT = 0
    STARTED = 1
    CONSTRUCTING = 2
    CONSTRUCTED = 3
    TX = 4
    COMMIT = 5
    OK = 6
    ERROR = 7
    VIOLATION = 8
    EVENT = 9
    ABORT = 10
    LOG = 11
    SEEN = 12

cmds = {
    "started": State.STARTED,
    "constructing": State.CONSTRUCTING,
    "constructed": State.CONSTRUCTED,
    "tx": State.TX,
    "cmt": State.COMMIT,
    "brt": State.ABORT,
    "ok": State.OK,
    "err": State.ERROR,
    "event": State.EVENT,
    "violation": State.VIOLATION,
    "log": State.LOG,
    "seen": State.SEEN
}

transitions = {
    State.INIT: [State.STARTED],
    State.STARTED: [State.CONSTRUCTING],
    State.CONSTRUCTING: [State.CONSTRUCTED, State.ERROR],
    State.CONSTRUCTED: [State.TX, State.CONSTRUCTING, State.SEEN],
    State.SEEN: [State.CONSTRUCTING, State.SEEN],
    State.TX: [State.ABORT, State.COMMIT, State.ERROR],
    State.ABORT: [State.OK, State.ERROR],
    State.COMMIT: [State.OK, State.ERROR],
    State.OK: [State.TX, State.CONSTRUCTING],
    State.ERROR: [State.TX, State.CONSTRUCTING]
}

phantoms = [ State.EVENT, State.VIOLATION, State.LOG ]