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
    WRITING = 12

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
    "writing": State.WRITING
}

transitions = {
    State.INIT: [State.STARTED],
    State.STARTED: [State.CONSTRUCTING],
    State.CONSTRUCTING: [State.CONSTRUCTED, State.ERROR],
    State.CONSTRUCTED: [State.WRITING, State.TX, State.CONSTRUCTING],
    State.WRITING: [State.OK, State.ERROR],
    State.TX: [State.ABORT, State.COMMIT, State.ERROR],
    State.ABORT: [State.OK, State.ERROR],
    State.COMMIT: [State.OK, State.ERROR],
    State.OK: [State.TX, State.WRITING, State.CONSTRUCTING],
    State.ERROR: [State.TX, State.CONSTRUCTING]
}

phantoms = [ State.EVENT, State.VIOLATION, State.LOG ]