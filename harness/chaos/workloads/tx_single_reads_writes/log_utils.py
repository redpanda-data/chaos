from enum import Enum

class State(Enum):
    INIT = 0
    STARTED = 1
    CONSTRUCTING = 2
    CONSTRUCTED = 3
    TX = 4
    OP = 5
    OFFSET = 6
    COMMIT = 7
    OK = 8
    ERROR = 9
    VIOLATION = 10
    EVENT = 11
    ABORT = 12

cmds = {
    "started": State.STARTED,
    "constructing": State.CONSTRUCTING,
    "constructed": State.CONSTRUCTED,
    "tx": State.TX,
    "op": State.OP,
    "idx": State.OFFSET,
    "cmt": State.COMMIT,
    "brt": State.ABORT,
    "ok": State.OK,
    "err": State.ERROR,
    "event": State.EVENT,
    "violation": State.VIOLATION
}

transitions = {
    State.INIT: [State.STARTED],
    State.STARTED: [State.CONSTRUCTING],
    State.CONSTRUCTING: [State.CONSTRUCTED, State.ERROR],
    State.CONSTRUCTED: [State.TX, State.CONSTRUCTING],
    State.TX: [State.OP],
    State.OP: [State.OFFSET, State.ABORT],
    State.OFFSET: [State.OP, State.COMMIT, State.ABORT],
    State.ABORT: [State.OK, State.ERROR],
    State.COMMIT: [State.OK, State.ERROR],
    State.OK: [State.TX, State.CONSTRUCTING],
    State.ERROR: [State.TX, State.CONSTRUCTING]
}

phantoms = [ State.EVENT, State.VIOLATION ]