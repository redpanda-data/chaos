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
    SEND = 12
    READ = 13
    SEEN = 14

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
    "send": State.SEND,
    "read": State.READ,
    "seen": State.SEEN
}

threads = {
    "producing": {
        State.STARTED: [State.CONSTRUCTING],
        State.CONSTRUCTING: [State.CONSTRUCTED, State.ERROR],
        State.CONSTRUCTED: [State.SEND, State.CONSTRUCTING],
        State.SEND: [State.OK, State.ERROR],
        State.OK: [State.SEND, State.CONSTRUCTING],
        State.ERROR: [State.CONSTRUCTING]
    },
    "streaming": {
        State.STARTED: [State.CONSTRUCTING],
        State.CONSTRUCTING: [State.CONSTRUCTED, State.ERROR],
        State.CONSTRUCTED: [State.READ, State.CONSTRUCTING],
        State.READ: [State.CONSTRUCTING, State.TX],
        State.TX: [State.ABORT, State.COMMIT, State.ERROR],
        State.ABORT: [State.OK, State.ERROR],
        State.COMMIT: [State.OK, State.ERROR],
        State.OK: [State.READ, State.CONSTRUCTING],
        State.ERROR: [State.CONSTRUCTING]
    },
    "consuming": {
        State.STARTED: [State.CONSTRUCTING],
        State.CONSTRUCTING: [State.CONSTRUCTED, State.ERROR],
        State.CONSTRUCTED: [State.CONSTRUCTING, State.SEEN],
        State.SEEN: [State.SEEN, State.CONSTRUCTING]
    }
}

phantoms = [ State.EVENT, State.VIOLATION, State.LOG ]