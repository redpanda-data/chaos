from enum import Enum

class State(Enum):
    STARTED = 0
    CONSTRUCTING = 1
    ERROR = 2
    CONSTRUCTED = 3
    SEND = 4
    OK = 5
    POLL = 6
    READ = 7
    SEEN = 8
    COMMIT = 9
    EVENT = 10
    VIOLATION = 11
    LOG = 12

cmds = {
    "started": State.STARTED,
    "constructing": State.CONSTRUCTING,
    "constructed": State.CONSTRUCTED,
    "ok": State.OK,
    "err": State.ERROR,
    "event": State.EVENT,
    "violation": State.VIOLATION,
    "log": State.LOG,
    "send": State.SEND,
    "poll": State.POLL,
    "read": State.READ,
    "seen": State.SEEN,
    "commit": State.COMMIT
}

threads = {
    "producing": {
        State.STARTED: [State.CONSTRUCTING],
        State.CONSTRUCTING: [State.CONSTRUCTED, State.ERROR],
        State.CONSTRUCTED: [State.SEND],
        State.SEND: [State.OK, State.ERROR],
        State.OK: [State.SEND],
        State.ERROR: [State.CONSTRUCTING]
    },
    "consuming": {
        State.STARTED: [State.CONSTRUCTING],
        State.CONSTRUCTING: [State.CONSTRUCTED, State.ERROR],
        State.CONSTRUCTED: [State.POLL],
        State.POLL: {
            State.OK: [State.POLL, State.READ],
            State.ERROR: [State.CONSTRUCTING],
        },
        State.READ: [State.POLL, State.COMMIT, State.READ, State.SEEN, State.CONSTRUCTING],
        State.COMMIT: {
            State.OK: [State.SEEN, State.READ],
            State.ERROR: [State.CONSTRUCTING]
        },
        State.SEEN: [State.READ, State.POLL]
    }
}

phantoms = [ State.EVENT, State.VIOLATION, State.LOG ]